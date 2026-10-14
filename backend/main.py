"""FastAPI app.

Options for forms:  /meta/options
Organizations:      /organizations, /organizations/{org_id}/config
Accounts per org:   /organizations/{org_id}/accounts
Fetch (Refresh):    /organizations/{org_id}/fetch
Results:            /organizations/{org_id}/results (everything the dashboard needs), /overview, /gaps,
                    /speed, /performance, /topics, /recommendations
Performance:        /organizations/{org_id}/dashboard (summary, trend, insights, YouTube and website sections)
Content Explorer:   /organizations/{org_id}/content, /collections (+ /items)
History:            /organizations/{org_id}/history, /organizations/{org_id}/posts/{post_id}/history
Competitors:        /organizations/{org_id}/dna (Content DNA), /changes (Change Detector)
Opportunities:      /organizations/{org_id}/opportunities (+ /{opp_id}, /brief, /mediaops, /calendar.ics, /evaluate)
Experiments:        /organizations/{org_id}/experiments (+ /{exp_id}, /evaluate), strategies included in the list
Overview:           /organizations/{org_id}/briefing (plain-language briefing + charts; POST /briefing/ai for the AI one)
Trends:             /organizations/{org_id}/trends (+ POST /trends/refresh)

    run_api.bat      then open http://localhost:8000/docs
"""
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, delete, func, select

import ai
import changes as change_detector
import config
import connectors
import dashboard
import dna
import experiments as exps
import insights
import integrations
import mediaops
import opportunities as opps
import recommend
import social_http
import social_routes
import trends
import workspace
import youtube
from analysis import analyse
from dataset import Dataset, iso, utc
from db import create_tables, get_session
from fetcher import fetch_org
from models import (ACCOUNT_GROUPS, EXPERIMENT_STATUSES, AccountSnapshot, AudienceQuestion, ChangeEvent,
                    CollectionItem, Competitor, Experiment, MetricSnapshot, OAuthState, Opportunity, Organization,
                    Post, SocialConnection, TrendItem)
from performance import compare
from topics import GAP_STATUSES, STATUS_LABELS

app = FastAPI(title="MediaOps Competitive Tracker")
app.add_middleware(
    CORSMiddleware,
    # Any port on this computer: Vite moves to 5174, 5175... when 5173 is already taken.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|\[::1\]):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(social_routes.router)  # Instagram, Facebook and X sign-in


@app.get("/", include_in_schema=False)
def home():
    """Opening the API address in a browser shows the API test page instead of "Not Found"."""
    return RedirectResponse("/docs")


@app.on_event("startup")
def on_startup():
    create_tables()


@app.get("/meta/options")
def meta_options():
    """Choices for the workspace form and what each platform can measure."""
    return {**workspace.options(), "platforms": connectors.describe(),
            "account_groups": [{"id": k, "label": v} for k, v in ACCOUNT_GROUPS.items()],
            "experiment_metrics": [{"id": k, **v} for k, v in exps.TARGET_METRICS.items()],
            "youtube_quota": {"used_today": youtube.units_used(), "left": youtube.budget_left()},
            "trends": {"google_trends": config.TRENDS_GOOGLE_TRENDS, "google_news": config.TRENDS_GOOGLE_NEWS,
                       "youtube_trending": bool(youtube.YOUTUBE_API_KEY)},
            "ai_available": ai.configured(),
            "mediaops_api": mediaops.configured()}


# ---- Organizations (workspaces) ----

class TopicRules(BaseModel):
    aliases: dict[str, str] = {}   # term -> label to show instead (rename, or merge into another topic)
    excluded: list[str] = []       # terms that aren't real topics


class WorkspaceIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    creator_type: Optional[str] = None
    category: Optional[str] = None  # industry id
    niche: Optional[str] = Field(default=None, max_length=120)
    sub_niche: Optional[str] = Field(default=None, max_length=120)
    audience: Optional[str] = Field(default=None, max_length=300)
    topic_rules: Optional[TopicRules] = None
    goals: Optional[list[str]] = None
    topics: Optional[list[str]] = None
    formats: Optional[list[str]] = None
    platforms: Optional[list[str]] = None
    timezone: Optional[str] = None
    time_sensitive: Optional[bool] = None
    window_hours: Optional[int] = None
    region: Optional[str] = None        # country for internet trends
    brand_safety: Optional[str] = None  # how sensitive news is handled


class OrganizationIn(WorkspaceIn):
    name: str
    category: str = "news"
    window_hours: Optional[int] = None


def _apply_config(org, data: WorkspaceIn):
    """Validate and copy the workspace fields that were sent."""
    sent = data.model_dump(exclude_unset=True)
    if "creator_type" in sent and sent["creator_type"] not in (None, *workspace.CREATOR_TYPES):
        raise HTTPException(400, "Choose a creator/business type from the list.")
    if "category" in sent:
        cat = workspace.LEGACY_CATEGORIES.get(sent["category"], sent["category"])
        if cat not in workspace.INDUSTRIES:
            raise HTTPException(400, "Choose an industry from the list (or Other).")
        sent["category"] = cat
    for field, allowed in (("goals", workspace.GOALS), ("formats", workspace.FORMATS)):
        if sent.get(field) is not None:
            bad = [x for x in sent[field] if x not in allowed]
            if bad:
                raise HTTPException(400, f"Unknown {field}: {', '.join(bad)}")
    if sent.get("topics") is not None:
        cleaned = []
        for t in sent["topics"]:
            t = " ".join(t.split())
            if len(t) > 60:
                raise HTTPException(400, f'Topic "{t[:30]}…" is too long (60 characters max).')
            if t and t.lower() not in {c.lower() for c in cleaned}:
                cleaned.append(t)
        if len(cleaned) > 40:
            raise HTTPException(400, "Up to 40 topics or keywords.")
        sent["topics"] = cleaned
    if sent.get("platforms") is not None:
        known = set(connectors.CONNECTORS) | set(connectors.PLANNED)
        if any(p not in known for p in sent["platforms"]):
            raise HTTPException(400, "Unknown platform.")
    if sent.get("timezone"):
        try:
            ZoneInfo(sent["timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(400, "Unknown time zone. Use a name like Asia/Kolkata or America/New_York.")
    if sent.get("region"):
        sent["region"] = sent["region"].upper()
        if sent["region"] not in workspace.REGIONS:
            raise HTTPException(400, "Choose a country from the list.")
    if sent.get("brand_safety") and sent["brand_safety"] not in workspace.BRAND_SAFETY:
        raise HTTPException(400, "Choose a brand-safety level from the list.")
    if sent.get("window_hours") is not None and not 1 <= sent["window_hours"] <= 24 * 90:
        raise HTTPException(400, "The time window must be between 1 hour and 90 days.")
    if sent.get("topic_rules") is not None:
        rules = sent["topic_rules"]
        clean = lambda t: " ".join(str(t).lower().split())  # noqa: E731
        aliases = {clean(k): " ".join(str(v).split()) for k, v in rules.get("aliases", {}).items()
                   if clean(k) and " ".join(str(v).split()) and clean(k) != clean(v)}
        excluded = sorted({clean(t) for t in rules.get("excluded", []) if clean(t)})
        if len(aliases) > 200 or len(excluded) > 300 or any(len(x) > 60 for x in [*aliases, *aliases.values(), *excluded]):
            raise HTTPException(400, "Too many topic corrections, or a topic longer than 60 characters.")
        sent["topic_rules"] = {"aliases": aliases, "excluded": excluded}
    for k in ("niche", "sub_niche", "audience"):
        if k in sent and sent[k] is not None:
            sent[k] = sent[k].strip() or None
    for k, v in sent.items():
        if k != "name" and (v is not None or k in ("niche", "sub_niche", "audience", "creator_type", "time_sensitive", "brand_safety")):
            setattr(org, k, v)


@app.get("/organizations")
def list_organizations(session: Session = Depends(get_session)):
    return session.exec(select(Organization).order_by(Organization.name)).all()


@app.post("/organizations", status_code=201)
def add_organization(data: OrganizationIn, session: Session = Depends(get_session)):
    name = data.name.strip()
    if not name:
        raise HTTPException(400, "Enter an organization name.")
    if session.exec(select(Organization).where(Organization.name == name)).first():
        raise HTTPException(400, "An organization with this name already exists.")
    org = Organization(name=name, category=data.category)
    _apply_config(org, data)
    org.category = workspace.industry_id(org)
    if not data.window_hours:  # default from the industry: news 24 hours, most creators 2-4 weeks
        org.window_hours = workspace.INDUSTRIES[org.category][1]
    if data.goals is None and org.creator_type:  # starting goals for this kind of business; editable
        org.goals = list(workspace.profile(org.creator_type)["goals"])
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


@app.get("/organizations/{org_id}/config")
def get_config(org_id: int, session: Session = Depends(get_session)):
    return workspace.config(_org(session, org_id))


@app.put("/organizations/{org_id}/config")
def update_config(org_id: int, data: WorkspaceIn, session: Session = Depends(get_session)):
    org = _org(session, org_id)
    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise HTTPException(400, "Enter a workspace name.")
        other = session.exec(select(Organization).where(Organization.name == name, Organization.id != org_id)).first()
        if other:
            raise HTTPException(400, "Another workspace already has this name.")
        org.name = name
    _apply_config(org, data)
    session.add(org)
    session.commit()
    session.refresh(org)
    return {"organization": org, "config": workspace.config(org)}


@app.delete("/organizations/{org_id}", status_code=204)
def remove_organization(org_id: int, session: Session = Depends(get_session)):
    org = _org(session, org_id)
    for c in session.exec(select(Competitor).where(Competitor.org_id == org_id)).all():
        _delete_account_data(session, c.id)
        session.delete(c)
    for table in (Opportunity, CollectionItem, ChangeEvent, Experiment, SocialConnection, OAuthState, TrendItem):
        session.exec(delete(table).where(table.org_id == org_id))
    session.delete(org)
    session.commit()


def _org(session, org_id):
    org = session.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organization not found.")
    return org


def _delete_account_data(session, account_id):
    post_ids = [p.id for p in session.exec(select(Post).where(Post.competitor_id == account_id)).all()]
    if post_ids:
        session.exec(delete(MetricSnapshot).where(MetricSnapshot.post_id.in_(post_ids)))
        session.exec(delete(AudienceQuestion).where(AudienceQuestion.post_id.in_(post_ids)))
        session.exec(delete(CollectionItem).where(CollectionItem.post_id.in_(post_ids)))
    session.exec(delete(ChangeEvent).where(ChangeEvent.account_id == account_id))
    session.exec(delete(AccountSnapshot).where(AccountSnapshot.competitor_id == account_id))
    session.exec(delete(Post).where(Post.competitor_id == account_id))


# ---- Accounts (ours and competitors') ----

class AccountIn(BaseModel):
    name: str = ""  # optional for Instagram / Facebook / X: filled from the profile when left empty
    platform: str = "rss"
    source: str
    is_us: bool = False
    group: Optional[str] = None


class AccountPatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    source: Optional[str] = Field(default=None, max_length=500)
    group: Optional[str] = None


def _check_group(group, is_us):
    if group is None or group == "":
        return None
    if is_us:
        raise HTTPException(400, "Groups are for competitors, not your own accounts.")
    if group not in ACCOUNT_GROUPS:
        raise HTTPException(400, f"Choose a group: {', '.join(ACCOUNT_GROUPS.values())}.")
    return group


def _public_url(a):
    """The account's public page: the YouTube channel, the profile / Page, or the feed link for websites."""
    connector = connectors.CONNECTORS.get(a.platform)
    if connector and hasattr(connector, "profile_url"):
        return connector.profile_url(a)
    if a.platform == "youtube" and a.channel_id:
        return f"https://www.youtube.com/channel/{a.channel_id}"
    return a.source if a.source.lower().startswith(("http://", "https://")) else None


@app.get("/organizations/{org_id}/accounts")
def list_accounts(org_id: int, session: Session = Depends(get_session)):
    ds = _dataset(session, org_id)
    accounts = sorted(ds.accounts, key=lambda a: (not a.is_us, a.name.lower(), a.platform))
    # Connection state only (no API call, no token refresh), for the status column.
    ready = {p: integrations.is_connected(session, org_id, p) for p in integrations.PLATFORMS}
    out = []
    for a in accounts:
        mine = [p for p in ds.posts if p.competitor_id == a.id]
        with_views = sum(1 for p in mine if p.views is not None)
        b = ds.baseline.get(a.id)
        social = a.platform in integrations.PLATFORMS
        if social and not integrations.configured(a.platform):
            health = {"state": "not_configured", "label": "Not configured",
                      "detail": "Add API credentials to enable this integration."}
        elif social and not ready.get(a.platform):
            health = {"state": "pending", "label": "Waiting for connection",
                      "detail": integrations.not_ready_reason(session, org_id, a.platform)}
        elif social and a.verified is False and not a.last_error:
            health = {"state": "unverified", "label": "Unverified",
                      "detail": "Saved but not yet confirmed with the platform. It's checked on the next Refresh."}
        elif a.last_error:
            health = {"state": "failed", "label": "Last refresh failed", "detail": a.last_error}
        elif not a.last_fetched_at:
            health = {"state": "pending", "label": "Not refreshed yet", "detail": "Click Refresh to collect posts."}
        elif a.platform == "youtube" and not b:
            health = {"state": "limited", "label": "Not enough history",
                      "detail": "Needs 5+ videos at least 48 hours old (last 90 days) before 'vs usual' can be calculated."}
        elif a.platform != "youtube" and len(mine) < 5:
            health = {"state": "limited", "label": "Few posts", "detail": f"Only {len(mine)} posts collected so far."}
        else:
            health = {"state": "ok", "label": "Collecting", "detail": None}
        # SQLite drops the time zone; send UTC explicitly so browsers don't read it as local time.
        out.append({**a.model_dump(), "last_fetched_at": iso(a.last_fetched_at), "public_url": _public_url(a),
                    "posts": len(mine), "posts_with_views": with_views, "baseline": b, "health": health,
                    "group_label": ACCOUNT_GROUPS.get(a.group) if a.group else None})
    return out


@app.post("/organizations/{org_id}/accounts", status_code=201)
def add_account(org_id: int, data: AccountIn, session: Session = Depends(get_session)):
    _org(session, org_id)
    name, source = data.name.strip(), data.source.strip()
    social = data.platform in integrations.PLATFORMS
    if not source or (not name and not social):
        raise HTTPException(400, "Enter a name and a link or handle.")
    try:
        connector = connectors.get(data.platform)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if data.platform == "rss" and not source.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "The RSS link must start with http:// or https://")
    same_org = select(Competitor).where(Competitor.org_id == org_id, Competitor.platform == data.platform)
    if data.is_us:
        current = session.exec(same_org.where(Competitor.is_us == True)).first()  # noqa: E712
        if current:
            raise HTTPException(400, f'"{current.name}" is already our {_label(data.platform)}. Remove it first.')

    account = Competitor(org_id=org_id, name=name, platform=data.platform, source=source, is_us=data.is_us,
                         group=_check_group(data.group, data.is_us))
    found = _resolve(session, org_id, connector, source)  # check the account exists before saving
    note = found.pop("note", None)
    display_name = found.pop("display_name", None)
    if not account.name:  # name left empty: use the profile's name, or the handle
        account.name = (display_name or found.get("source") or source)[:80]
    for k, v in found.items():
        setattr(account, k, v)
    duplicate = _duplicate(session, same_org, account)
    if duplicate:
        raise HTTPException(400, f"This {_label(data.platform)} is already added as \"{duplicate.name}\".")

    session.add(account)
    session.commit()
    session.refresh(account)
    return {**account.model_dump(), "note": note}


def _resolve(session, org_id, connector, source):
    """Check an account with its platform. Instagram / Facebook / X accounts that can't be checked yet
    (platform not configured or not connected) are returned as unverified, without any API call."""
    needs = getattr(connector, "requires_connection", False)
    ctx = integrations.context(session, org_id, connector.id) if needs else None
    try:
        return connector.resolve(source, ctx) if needs else connector.resolve(source)
    except social_http.TokenInvalid as exc:
        conn = integrations.connection(session, org_id, connector.id)
        if conn:
            integrations.mark_invalid(session, conn, str(exc))
        return {**connector.resolve(source, None), "note": str(exc)}
    except social_http.RateLimited as exc:
        return {**connector.resolve(source, None), "note": f"{exc} Saved as unverified; it's checked on the next Refresh."}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def _duplicate(session, same_org, account):
    """The same account already in this workspace: same platform id, or the same handle / link."""
    if account.channel_id:
        return session.exec(same_org.where(Competitor.channel_id == account.channel_id)).first()
    if account.external_id:
        hit = session.exec(same_org.where(Competitor.external_id == account.external_id)).first()
        if hit:
            return hit
    return session.exec(same_org.where(func.lower(Competitor.source) == account.source.lower())).first()


@app.patch("/organizations/{org_id}/accounts/{account_id}")
def edit_account(org_id: int, account_id: int, data: AccountPatch, session: Session = Depends(get_session)):
    """Rename, regroup, or point an account at a different link (checked before saving)."""
    account = _account(session, org_id, account_id)
    sent = data.model_dump(exclude_unset=True)
    if "name" in sent:
        name = (sent["name"] or "").strip()
        if not name:
            raise HTTPException(400, "Enter a name.")
        account.name = name
    if "group" in sent:
        account.group = _check_group(sent["group"], account.is_us)
    if sent.get("source") is not None and sent["source"].strip() != account.source:
        source = sent["source"].strip()
        found = _resolve(session, org_id, connectors.get(account.platform), source)
        found.pop("note", None)
        found.pop("display_name", None)
        probe = Competitor(org_id=org_id, name=account.name, platform=account.platform,
                           source=found.get("source", source), channel_id=found.get("channel_id"),
                           external_id=found.get("external_id"))
        same = select(Competitor).where(Competitor.org_id == org_id, Competitor.platform == account.platform,
                                        Competitor.id != account.id)
        clash = _duplicate(session, same, probe)
        if clash:
            raise HTTPException(400, f'This {_label(account.platform)} is already added as "{clash.name}".')
        same_account = ((found.get("channel_id") and found.get("channel_id") == account.channel_id)
                        or (found.get("external_id") and found.get("external_id") == account.external_id))
        if not same_account:
            _delete_account_data(session, account.id)  # different account: old posts don't belong to it
            account.last_fetched_at = None
            account.external_id = None
        account.source = source
        for k, v in found.items():
            setattr(account, k, v)
        account.last_error = None
    session.add(account)
    session.commit()
    session.refresh(account)
    return {**account.model_dump(), "last_fetched_at": iso(account.last_fetched_at)}


def _account(session, org_id, account_id):
    account = session.get(Competitor, account_id)
    if not account or account.org_id != org_id:
        raise HTTPException(404, "Account not found.")
    return account


@app.delete("/organizations/{org_id}/accounts/{account_id}", status_code=204)
def remove_account(org_id: int, account_id: int, session: Session = Depends(get_session)):
    account = _account(session, org_id, account_id)
    _delete_account_data(session, account_id)
    session.delete(account)
    session.commit()


@app.get("/youtube/suggest")
def youtube_suggest(q: str):
    """Channels matching what the user is typing, with logo, handle and subscribers."""
    try:
        return youtube.suggest_channels(q)
    except ValueError as exc:
        raise HTTPException(502, str(exc))


ACCOUNT_NOUNS = {"youtube": "YouTube channel", "rss": "RSS feed", "instagram": "Instagram account",
                 "facebook": "Facebook Page", "x": "X account"}


def _label(platform):
    return ACCOUNT_NOUNS.get(platform, "account")


# ---- Fetch and results ----

@app.post("/organizations/{org_id}/fetch")
def fetch(org_id: int, session: Session = Depends(get_session)):
    org = _org(session, org_id)
    result = fetch_org(session, org_id)
    # Trends are read on every Refresh too (cached for an hour); a failure never blocks the posts.
    try:
        result["trends"] = trends.refresh(session, org, trends.competitor_topics(_dataset(session, org_id)))
    except Exception as exc:  # noqa: BLE001 - trends are optional
        session.rollback()
        result["trends"] = {"error": str(exc)[:200]}
    return result


def _load(session, org_id):
    org = _org(session, org_id)
    accounts = session.exec(select(Competitor).where(Competitor.org_id == org_id)).all()
    ids = [a.id for a in accounts]
    posts = session.exec(select(Post).where(Post.competitor_id.in_(ids))).all() if ids else []
    return org, accounts, posts


def _dataset(session, org_id, now=None, days=None, competitor_id=None):
    """days: period other than the workspace window. competitor_id: our accounts + that competitor only
    (all accounts with the same name, so one competitor's YouTube and website stay together)."""
    org, accounts, posts = _load(session, org_id)
    if competitor_id:
        chosen = next((a for a in accounts if a.id == competitor_id and not a.is_us), None)
        if not chosen:
            raise HTTPException(404, "Competitor not found.")
        accounts = [a for a in accounts if a.is_us or a.name == chosen.name]
    post_ids = [p.id for p in posts]
    questions = session.exec(select(AudienceQuestion).where(AudienceQuestion.post_id.in_(post_ids))).all() if post_ids else []
    return Dataset(org, accounts, posts, questions, now, days)


def _audience_snaps(session, account_ids):
    """{account_id: [(captured_at UTC, subscribers)]} from the snapshots saved at each Refresh."""
    out = {}
    if account_ids:
        for s in session.exec(select(AccountSnapshot).where(AccountSnapshot.competitor_id.in_(account_ids))
                              .order_by(AccountSnapshot.captured_at)).all():
            out.setdefault(s.competitor_id, []).append((utc(s.captured_at), s.subscribers))
    return out


def _trend_items(session, ds):
    return trends.load(session, ds, trends.competitor_topics(ds))


def _analyse_all(session, org_id, with_trends=False):
    ds = _dataset(session, org_id)
    news = analyse(ds.posts, ds.accounts, window_hours=ds.org.window_hours)
    perf = compare(ds.accounts, ds.posts, gaps_count=len(news["gaps"]), tz=ds.tz)
    trend_items = _trend_items(session, ds)
    recs = recommend.build(ds, perf, opps.learned_stats(session, org_id), trend_items)
    if with_trends:
        return ds, news, perf, recs, trend_items
    return ds, news, perf, recs


def _topic_reason(ds, t, relevance):
    """Is this topic a potential opportunity for THIS workspace, and why (or why not)?"""
    score, why = relevance
    n_comp = len(t["competitors"])
    if t["status"] not in GAP_STATUSES:
        return False, {"covered": "You already cover this about as much as competitors.",
                       "limited_competitor_coverage": "Few of the competitors you track post about it.",
                       "no_posts_tracked": "No tracked account has posted about it in this period."}.get(t["status"], "")
    if t["competitor_posts"] < 2:
        return False, "Only one competitor post: not enough to call it a gap."
    if n_comp < 2 and score <= 1.0:
        return False, ("Only one competitor covers it and it doesn't match your workspace topics or niche, "
                       "so it may just be that account's own subject.")
    parts = [f"{n_comp} competitor{'s' if n_comp != 1 else ''} posted {t['competitor_posts']} times about it"]
    parts.append({"not_covered_by_you": "you haven't", "covered_less": f"you posted {t['our_posts']} times",
                  "covered_underperforming": f"your posts got {t['our_median_relative']}× your usual views"}[t["status"]])
    text = "; ".join(parts) + "."
    if t["median_relative"] is not None and t["median_relative"] >= 1.2:
        text += f" Their posts on it beat their usual views ({t['median_relative']}×)."
    if why:
        text += f" {why}"
    return True, text


def _topic_rows(ds):
    rows, our_total = ds.topics()
    words = recommend._relevance_words(ds.cfg)
    out = []
    for t in rows:
        relevance = recommend.topic_relevance(ds, t, words) if t["competitor_posts"] else (1.0, None)
        opportunity, reason = _topic_reason(ds, t, relevance)
        out.append({**{k: v for k, v in t.items() if k != "post_ids"},
                    "latest": iso(t["latest"]), "status_label": STATUS_LABELS[t["status"]],
                    "posts": len(t["post_ids"]), "relevant": relevance[0] > 1.0,
                    "opportunity": opportunity, "reason": reason,
                    "examples": [ds.post_card(ds.post_by_id[i]) for i in t["post_ids"][:3]]})
    return out, our_total


@app.get("/organizations/{org_id}/results")
def results(org_id: int, session: Session = Depends(get_session)):
    """Everything the dashboard needs in one call."""
    ds, news, perf, recs = _analyse_all(session, org_id)
    topic_rows, _ = _topic_rows(ds)
    to_review = sum(1 for t in topic_rows if t["opportunity"])  # same rule as the Coverage Gaps page
    overview = {**news["overview"], "topics_to_review": to_review, "questions": len(ds.questions)}
    return {"organization": ds.org, "config": ds.cfg, **news, "overview": overview, "performance": perf,
            "recommendations": recs, "readiness": recommend.readiness(ds, perf),
            "period": ds.period(), "freshness": ds.freshness()}


@app.get("/organizations/{org_id}/overview")
def get_overview(org_id: int, session: Session = Depends(get_session)):
    org, accounts, posts = _load(session, org_id)
    return analyse(posts, accounts, window_hours=org.window_hours)["overview"]


@app.get("/organizations/{org_id}/gaps")
def get_gaps(org_id: int, session: Session = Depends(get_session)):
    org, accounts, posts = _load(session, org_id)
    return analyse(posts, accounts, window_hours=org.window_hours)["gaps"]


@app.get("/organizations/{org_id}/speed")
def get_speed(org_id: int, session: Session = Depends(get_session)):
    org, accounts, posts = _load(session, org_id)
    return analyse(posts, accounts, window_hours=org.window_hours)["speed"]


@app.get("/organizations/{org_id}/performance")
def get_performance(org_id: int, session: Session = Depends(get_session)):
    org, accounts, posts = _load(session, org_id)
    gaps = analyse(posts, accounts, window_hours=org.window_hours)["gaps"]
    return compare(accounts, posts, gaps_count=len(gaps), tz=workspace.tz(org))


@app.get("/organizations/{org_id}/topics")
def get_topics(org_id: int, days: Optional[int] = Query(default=None, ge=1, le=365),
               competitor_id: Optional[int] = None, session: Session = Depends(get_session)):
    """Topic coverage map for the comparison period (or `days`), optionally against one competitor."""
    ds = _dataset(session, org_id, days=days, competitor_id=competitor_id)
    rows, our_total = _topic_rows(ds)
    return {"topics": rows, "your_posts_checked": our_total, "competitor_posts_checked": len([p for p in ds.recent if not ds.is_us(p)]),
            "period": ds.period(), "freshness": ds.freshness(), "status_labels": STATUS_LABELS,
            "rules": ds.cfg["topic_rules"],
            "competitors": [{"id": a.id, "name": a.name, "platform": a.platform}
                            for a in _load(session, org_id)[1] if not a.is_us],
            "method": ("Topics are words, two-word phrases and creator tags shared by several accounts, plus your workspace topics. "
                       "Topics whose posts mostly overlap are grouped together. Matching is by keywords, so different wording "
                       "for the same idea isn't joined: rename or merge topics to correct it.")}


# ---- Performance dashboard ----

@app.get("/organizations/{org_id}/dashboard")
def get_dashboard(org_id: int, days: int = Query(default=90, ge=7, le=365), competitor_id: Optional[int] = None,
                  format: Optional[str] = Query(default=None, max_length=20),
                  platform: Optional[str] = Query(default=None, max_length=20),
                  topic: Optional[str] = Query(default=None, max_length=60), session: Session = Depends(get_session)):
    """Performance overview for the chosen period and filters: everything comes from the same posts."""
    ds = _dataset(session, org_id, days=days, competitor_id=competitor_id)
    full = _dataset(session, org_id)
    perf = compare(full.accounts, full.posts, tz=full.tz)
    recs = recommend.build(full, perf, opps.learned_stats(session, org_id))
    out = dashboard.build(ds, ds.posts, fmt=format, topic=topic, platform=platform, recs=recs,
                          audience_snaps=_audience_snaps(session, [a.id for a in ds.accounts]),
                          social_configured={p: integrations.configured(p) for p in integrations.PLATFORMS})
    out["facets"] = {
        "competitors": [{"id": a.id, "name": a.name, "platform": a.platform} for a in full.accounts if not a.is_us],
        "platforms": sorted({a.platform for a in full.accounts}),
        "formats": sorted({ds.format(p) for p in ds.posts if ds.format(p)}),
        "topics": [t["topic"] for t in full.topics()[0][:40]],
    }
    return out


# ---- Overview (plain-language briefing), trends and the optional AI briefing ----

@app.get("/organizations/{org_id}/briefing")
def briefing(org_id: int, session: Session = Depends(get_session)):
    """The Overview tab: plain-language briefing, KPIs and chart data for the period."""
    ds, _, perf, recs, trend_items = _analyse_all(session, org_id, with_trends=True)
    ids = [a.id for a in ds.accounts]
    snaps = {}
    if ids:
        for sn in session.exec(select(AccountSnapshot).where(AccountSnapshot.competitor_id.in_(ids))).all():
            snaps.setdefault(sn.competitor_id, []).append(sn)
    return {**insights.build(ds, perf, recs, trend_items, snaps), "config": ds.cfg, "ai_available": ai.configured()}


@app.post("/organizations/{org_id}/briefing/ai")
def ai_briefing(org_id: int, session: Session = Depends(get_session)):
    """Optional: Claude rewrites the briefing and suggests content ideas from the Overview's numbers."""
    data = briefing(org_id, session)
    try:
        return ai.briefing(org_id, insights.ai_input(data, data["config"]))
    except ValueError as exc:
        raise HTTPException(400 if not ai.configured() else 502, str(exc))


@app.get("/organizations/{org_id}/trends")
def get_trends(org_id: int, session: Session = Depends(get_session)):
    """Trends that match this workspace, with sensitivity, competitor coverage and angles."""
    ds = _dataset(session, org_id)
    last = trends.last_refresh(session, org_id)
    return {"trends": _trend_items(session, ds), "last_refresh": iso(last), "config": ds.cfg,
            "sources": {"google_trends": config.TRENDS_GOOGLE_TRENDS, "google_news": config.TRENDS_GOOGLE_NEWS,
                        "youtube_trending": bool(youtube.YOUTUBE_API_KEY)},
            "method": "Trends come from Google's daily searches and Google News for your country, and YouTube Trending "
                      "for your industry's category. They're kept when they match your topics, niche, audience, industry "
                      "or your competitors' topics. Sensitivity is a keyword check that errs on the side of caution."}


@app.post("/organizations/{org_id}/trends/refresh")
def refresh_trends(org_id: int, session: Session = Depends(get_session)):
    org = _org(session, org_id)
    return trends.refresh(session, org, trends.competitor_topics(_dataset(session, org_id)), force=True)


@app.get("/organizations/{org_id}/recommendations")
def get_recommendations(org_id: int, session: Session = Depends(get_session)):
    ds, _, perf, recs = _analyse_all(session, org_id)
    return {"recommendations": recs, "readiness": recommend.readiness(ds, perf)}


# ---- Content Explorer ----

PERF_FILTERS = {"outlier": (2.0, None), "above": (1.2, None), "usual": (0.8, 1.2), "below": (None, 0.8)}


# Words too general to describe a niche when "My niche topics" is worked out from our own posts.
GENERIC_TOPIC_WORDS = {
    "against", "about", "after", "before", "little", "moments", "moment", "work", "soft", "best", "full",
    "part", "video", "videos", "live", "today", "news", "update", "latest", "watch", "first", "make",
    "with", "from", "this", "that", "your", "what", "when", "here", "more", "most", "just", "only",
    "every", "episode", "official", "shorts", "short", "vlog", "day", "days", "time", "look",
}


@app.get("/organizations/{org_id}/content")
def content(
    org_id: int,
    account_id: Optional[int] = None,
    platform: Optional[str] = None,
    topic: Optional[str] = None,
    format: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    performance: Optional[Literal["outlier", "above", "usual", "below", "unknown"]] = None,
    q: Optional[str] = Query(default=None, max_length=100),
    my_topics: bool = False,
    include_ours: bool = False,
    collection: Optional[str] = Query(default=None, max_length=60),
    sort: Literal["newest", "views", "engagement", "relative"] = "newest",
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    """Searchable gallery of collected posts (competitors', and ours if asked)."""
    ds = _dataset(session, org_id)
    saved = session.exec(select(CollectionItem).where(CollectionItem.org_id == org_id)).all()
    saved_in = {}
    for s in saved:
        saved_in.setdefault(s.post_id, []).append({"id": s.id, "collection": s.collection})
    topic_rows, _ = ds.topics()
    topics_of = {}
    for t in topic_rows:
        for pid in t["post_ids"]:
            topics_of.setdefault(pid, []).append(t["topic"])
    tracked = [t.lower() for t in ds.cfg["topics"]]
    # "My niche topics": the topics saved in Workspace settings; if none are saved,
    # the topics our own posts already cover (so the filter always works).
    if tracked:
        niche, niche_source = ds.cfg["topics"], "workspace"
        niche_ids = set()
    else:
        ours = [t for t in topic_rows if t["our_posts"] >= 2 and len(t["topic"]) >= 4
                and t["topic"] not in GENERIC_TOPIC_WORDS][:15]
        niche, niche_source = [t["topic"] for t in ours], "our_posts"
        niche_ids = {pid for t in ours for pid in t["post_ids"]}
    niche_terms = [t.lower() for t in niche]

    items = [p for p in ds.posts if include_ours or not ds.is_us(p)]
    if collection:
        in_coll = {s.post_id for s in saved if s.collection == collection}
        items = [p for p in ds.posts if p.id in in_coll]
    if account_id:
        items = [p for p in items if p.competitor_id == account_id]
    if platform:
        items = [p for p in items if p.platform == platform]
    if format:
        items = [p for p in items if ds.format(p) == format]
    if since:
        items = [p for p in items if utc(p.published_at) >= utc(since)]
    if until:
        items = [p for p in items if utc(p.published_at) <= utc(until)]
    if topic:
        tl = topic.lower()
        ids = next((set(t["post_ids"]) for t in topic_rows if t["topic"].lower() == tl), None)
        items = [p for p in items if (ids is not None and p.id in ids) or tl in p.title.lower()
                 or any(tl == x.lower() for x in (p.tags or []))]
    if my_topics:
        items = [p for p in items if p.id in niche_ids
                 or any(t in (p.title + " " + " ".join(p.tags or [])).lower() for t in niche_terms)]
    if q:
        ql = q.lower()
        items = [p for p in items if ql in p.title.lower() or any(ql in x.lower() for x in (p.tags or []))]
    if performance == "unknown":
        items = [p for p in items if ds.relative.get(p.id) is None]
    elif performance:
        lo, hi = PERF_FILTERS[performance]
        items = [p for p in items if ds.relative.get(p.id) is not None
                 and (lo is None or ds.relative[p.id] >= lo) and (hi is None or ds.relative[p.id] < hi)]

    def engagement(p):
        return (p.likes + (p.comments or 0)) / p.views if p.views and p.likes is not None else None

    # Posts without the sort's metric go last (unknown is not "lowest"), newest first among them.
    metric = {"newest": None, "views": lambda p: p.views, "engagement": engagement,
              "relative": lambda p: ds.relative.get(p.id)}[sort]
    items.sort(key=lambda p: utc(p.published_at), reverse=True)
    if metric:
        items.sort(key=lambda p: (metric(p) is not None, metric(p) or 0), reverse=True)
    page = items[offset:offset + limit]
    return {
        "total": len(items),
        "items": [{**ds.post_card(p), "topics": topics_of.get(p.id, [])[:6], "tags": (p.tags or [])[:8],
                   "engagement_rate": round(engagement(p) * 100, 2) if engagement(p) is not None else None,
                   "saved_in": saved_in.get(p.id, [])} for p in page],
        "facets": {
            "accounts": [{"id": a.id, "name": a.name, "platform": a.platform, "is_us": a.is_us} for a in ds.accounts],
            "platforms": sorted({a.platform for a in ds.accounts}),
            "formats": sorted({ds.format(p) for p in ds.posts if ds.format(p)}),
            "topics": [t["topic"] for t in topic_rows[:40]],
            "my_topics": niche,
            "my_topics_source": niche_source,  # "workspace" (saved in settings) or "our_posts" (derived)
            # Only offer sorts and filters the data can support.
            "has_views": any(p.views is not None for p in ds.posts),
            "has_engagement": any(engagement(p) is not None for p in ds.posts),
            "has_relative": bool(ds.relative),
            "collections": _collection_counts(saved),
        },
        "definitions": {"relative": "Views ÷ the same account's median views (posts 48h+ old, last 90 days). Blank when the platform has no views or the account has fewer than 5 such posts.",
                        "engagement": "(likes + comments) ÷ views, for posts with a public like count."},
        "freshness": ds.freshness(),
    }


# ---- Saved collections (Content Explorer) ----

DEFAULT_COLLECTIONS = ["Content Ideas", "Competitor Research", "Campaign Inspiration"]


class CollectionItemIn(BaseModel):
    collection: str = Field(min_length=1, max_length=60)
    post_id: int
    note: Optional[str] = Field(default=None, max_length=300)


def _collection_counts(saved):
    counts = {name: 0 for name in DEFAULT_COLLECTIONS}
    for s in saved:
        counts[s.collection] = counts.get(s.collection, 0) + 1
    return [{"name": k, "posts": v} for k, v in counts.items()]


@app.get("/organizations/{org_id}/collections")
def list_collections(org_id: int, session: Session = Depends(get_session)):
    _org(session, org_id)
    return _collection_counts(session.exec(select(CollectionItem).where(CollectionItem.org_id == org_id)).all())


@app.post("/organizations/{org_id}/collections/items", status_code=201)
def save_to_collection(org_id: int, data: CollectionItemIn, session: Session = Depends(get_session)):
    _org(session, org_id)
    name = " ".join(data.collection.split())
    post = session.get(Post, data.post_id)
    account = session.get(Competitor, post.competitor_id) if post else None
    if not post or not account or account.org_id != org_id:
        raise HTTPException(404, "Post not found.")
    existing = session.exec(select(CollectionItem).where(CollectionItem.org_id == org_id, CollectionItem.collection == name,
                                                         CollectionItem.post_id == data.post_id)).first()
    if existing:
        return existing  # already saved there: no duplicate
    item = CollectionItem(org_id=org_id, collection=name, post_id=data.post_id, note=data.note)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@app.delete("/organizations/{org_id}/collections/items/{item_id}", status_code=204)
def remove_from_collection(org_id: int, item_id: int, session: Session = Depends(get_session)):
    item = session.get(CollectionItem, item_id)
    if not item or item.org_id != org_id:
        raise HTTPException(404, "Saved item not found.")
    session.delete(item)
    session.commit()


# ---- History ----

@app.get("/organizations/{org_id}/history")
def history(org_id: int, days: int = Query(default=90, ge=1, le=365), session: Session = Depends(get_session)):
    """Saved public numbers over time: audience size per account and weekly median views of new posts."""
    ds = _dataset(session, org_id)
    since = ds.now - timedelta(days=days)
    out = []
    for a in ds.accounts:
        snaps = session.exec(select(AccountSnapshot).where(AccountSnapshot.competitor_id == a.id)
                             .order_by(AccountSnapshot.captured_at)).all()
        audience = [{"at": iso(s.captured_at), "subscribers": s.subscribers} for s in snaps
                    if utc(s.captured_at) >= since and s.subscribers is not None]
        weeks = {}
        for p in ds.posts:
            if p.competitor_id == a.id and utc(p.published_at) >= since:
                monday = (utc(p.published_at) - timedelta(days=utc(p.published_at).weekday())).date().isoformat()
                weeks.setdefault(monday, []).append(p)
        weekly = []
        for w in sorted(weeks):
            ps = weeks[w]
            views = sorted(p.views for p in ps if p.views is not None)
            rel = sorted(ds.relative[p.id] for p in ps if ds.relative.get(p.id) is not None)
            weekly.append({"week": w, "posts": len(ps), "median_views": views[len(views) // 2] if views else None,
                           "median_relative": rel[len(rel) // 2] if rel else None})
        growth = None
        if len(audience) >= 2 and audience[0]["subscribers"]:
            first, last = audience[0], audience[-1]
            growth = {"from": first["subscribers"], "to": last["subscribers"],
                      "change": last["subscribers"] - first["subscribers"], "since": first["at"]}
        out.append({"id": a.id, "name": a.name, "platform": a.platform, "is_us": a.is_us,
                    "audience": audience, "audience_growth": growth, "weekly": weekly,
                    "baseline": ds.baseline.get(a.id)})
    # Only posts from platforms that report views (website/RSS articles have none).
    our_recent = sorted((p for p in ds.posts if ds.is_us(p) and p.views is not None
                         and utc(p.published_at) >= ds.now - timedelta(days=30)),
                        key=lambda p: p.published_at, reverse=True)
    return {
        "days": days, "accounts": out,
        "our_recent_vs_baseline": [ds.post_card(p) for p in our_recent[:15]],
        "notes": ["Audience numbers are saved each time you click Refresh, so the history starts from your first refresh.",
                  "YouTube rounds subscriber counts, so small changes may not show.",
                  "Weekly median views use each post's latest view count. Older weeks have had more time to collect views."],
    }


@app.get("/organizations/{org_id}/posts/{post_id}/history")
def post_history(org_id: int, post_id: int, session: Session = Depends(get_session)):
    post = session.get(Post, post_id)
    account = session.get(Competitor, post.competitor_id) if post else None
    if not post or not account or account.org_id != org_id:
        raise HTTPException(404, "Post not found.")
    snaps = session.exec(select(MetricSnapshot).where(MetricSnapshot.post_id == post_id).order_by(MetricSnapshot.captured_at)).all()
    return {"post": {"id": post.id, "title": post.title, "link": post.link, "published_at": iso(post.published_at)},
            "snapshots": [{"at": iso(s.captured_at), "views": s.views, "likes": s.likes, "comments": s.comments} for s in snaps]}


# ---- Competitor Content DNA and Change Detector ----

@app.get("/organizations/{org_id}/dna")
def get_dna(org_id: int, account_id: Optional[int] = None, session: Session = Depends(get_session)):
    """Content DNA for one account, or for every account (to compare them)."""
    ds = _dataset(session, org_id)
    accounts = [a for a in ds.accounts if account_id is None or a.id == account_id]
    if account_id and not accounts:
        raise HTTPException(404, "Account not found.")
    return {"days": dna.DNA_DAYS, "profiles": [dna.profile(ds, a) for a in accounts], "freshness": ds.freshness()}


class ChangePatch(BaseModel):
    status: Literal["new", "reviewed", "saved"]


def _change_out(e):
    return {"id": e.id, "key": e.key, "kind": e.kind, "account_id": e.account_id, "title": e.title,
            **e.detail, "status": e.status, "first_seen_at": iso(e.first_seen_at)}


@app.get("/organizations/{org_id}/changes")
def list_changes(org_id: int, status: Optional[Literal["new", "reviewed", "saved"]] = None,
                 session: Session = Depends(get_session)):
    """Check the saved data for notable competitor changes, store new ones once, and list them."""
    ds = _dataset(session, org_id)
    found = change_detector.detect(ds, _audience_snaps(session, [a.id for a in ds.accounts]))
    known = {e.key: e for e in session.exec(select(ChangeEvent).where(ChangeEvent.org_id == org_id)).all()}
    for ev in found:
        if ev["key"] in known:
            continue  # the same change is never added twice
        row = ChangeEvent(org_id=org_id, **ev)
        session.add(row)
        known[ev["key"]] = row
    session.commit()
    rows = sorted(known.values(), key=lambda e: utc(e.first_seen_at), reverse=True)
    if status:
        rows = [e for e in rows if e.status == status]
    return {"changes": [_change_out(e) for e in rows[:60]],
            "counts": {s: sum(1 for e in known.values() if e.status == s) for s in ("new", "reviewed", "saved")},
            "freshness": ds.freshness(),
            "note": "Checked against the data saved at each Refresh, not in real time."}


@app.patch("/organizations/{org_id}/changes/{change_id}")
def update_change(org_id: int, change_id: int, data: ChangePatch, session: Session = Depends(get_session)):
    e = session.get(ChangeEvent, change_id)
    if not e or e.org_id != org_id:
        raise HTTPException(404, "Change not found.")
    e.status = data.status
    session.add(e)
    session.commit()
    session.refresh(e)
    return _change_out(e)


# ---- Opportunities ----

class OpportunityIn(BaseModel):
    """Save a recommendation by `key`, or build one on demand from a coverage-map `topic`
    or a collected `post_id` (Coverage Gaps, Content Explorer, the change feed)."""
    key: Optional[str] = None
    topic: Optional[str] = Field(default=None, max_length=120)
    post_id: Optional[int] = None
    action: Literal["save", "brief"] = "save"


class OpportunityPatch(BaseModel):
    status: Optional[str] = None
    brief: Optional[dict] = None
    planned_for: Optional[datetime] = None
    mediaops_ref: Optional[str] = Field(default=None, max_length=300)
    published_link: Optional[str] = Field(default=None, max_length=500)
    note: Optional[str] = Field(default=None, max_length=300)


class MediaOpsIn(BaseModel):
    platforms: list[str] = []
    user_token: Optional[str] = None  # the signed-in MediaOps user's token, passed through, never stored


PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _opp(session, org_id, opp_id):
    o = session.get(Opportunity, opp_id)
    if not o or o.org_id != org_id:
        raise HTTPException(404, "Opportunity not found.")
    return o


def _opp_out(o):
    return {**o.model_dump(), "planned_for": iso(o.planned_for), "created_at": iso(o.created_at),
            "updated_at": iso(o.updated_at)}


def _refresh_outcomes(session, ds, tracked):
    """Link published links to our posts and measure results once they are old enough."""
    changed = False
    for o in tracked:
        if o.status not in ("published", "evaluated"):
            continue
        if opps.match_published(session, o, list(ds.us_ids)):
            changed = True
        if o.published_post_id and o.status == "published":
            result = opps.evaluate(session, o, ds)
            if result and result != o.outcome:
                o.outcome = result
                if result["state"] == "evaluated":
                    opps.record(o, "evaluated", "Measured against your baseline.")
                changed = True
        if changed:
            session.add(o)
    if changed:
        session.commit()


@app.get("/organizations/{org_id}/opportunities")
def list_opportunities(org_id: int, session: Session = Depends(get_session)):
    ds, _, perf, recs = _analyse_all(session, org_id)
    tracked = session.exec(select(Opportunity).where(Opportunity.org_id == org_id)
                           .order_by(Opportunity.updated_at.desc())).all()
    _refresh_outcomes(session, ds, tracked)
    taken = {o.key for o in tracked}
    return {
        # Work on these first: High priority first, then by score within each level.
        "suggested": sorted((r for r in recs if r["actionable"] and r["key"] not in taken),
                            key=lambda r: (PRIORITY_RANK[r["priority"]["level"]], -r["score"])),
        "tracked": [_opp_out(o) for o in tracked],
        "learned": opps.learned_stats(session, org_id),
        "mediaops_api": mediaops.configured(),
        "readiness": recommend.readiness(ds, perf),
        "eval_after_days": opps.EVAL_AFTER_DAYS,
    }


@app.post("/organizations/{org_id}/opportunities", status_code=201)
def create_opportunity(org_id: int, data: OpportunityIn, session: Session = Depends(get_session)):
    if not (data.key or data.topic or data.post_id):
        raise HTTPException(400, "Send a recommendation key, a topic or a post.")
    ds, _, _, recs = _analyse_all(session, org_id)
    if data.key:
        rec = next((r for r in recs if r["key"] == data.key), None)
    elif data.topic:
        rec = recommend.topic_rec(ds, data.topic, opps.learned_stats(session, org_id))
    else:
        rec = recommend.post_rec(ds, data.post_id, opps.learned_stats(session, org_id))
    key = rec["key"] if rec else data.key
    # Same topic or post = same key, so it's never saved (or briefed) twice.
    existing = session.exec(select(Opportunity).where(Opportunity.org_id == org_id, Opportunity.key == key)).first() if key else None
    if existing and existing.status != "dismissed":
        return _opp_out(existing)
    if not rec:
        raise HTTPException(404, "This recommendation is no longer in the data. Click Refresh and try again."
                            if data.key else "No competitor posts about this in the tracked data, so there's no evidence for a brief.")
    o = existing or Opportunity(org_id=org_id, key=rec["key"], kind=rec["kind"], title=rec["title"], snapshot=rec, history=[])
    if existing:
        o.snapshot = rec
        opps.record(o, "saved", "Restored")
    else:
        o.history = [{"status": "saved", "at": iso(o.created_at), "note": None}]
    if data.action == "brief":
        o.brief = opps.make_brief(rec, ds.cfg, _our_baseline(ds))
        opps.record(o, "brief")
    session.add(o)
    session.commit()
    session.refresh(o)
    return _opp_out(o)


def _our_baseline(ds):
    bases = [ds.baseline[a] for a in ds.us_ids if a in ds.baseline]
    return max(bases, key=lambda b: b["posts"]) if bases else None


@app.post("/organizations/{org_id}/opportunities/{opp_id}/brief")
def generate_brief(org_id: int, opp_id: int, session: Session = Depends(get_session)):
    o = _opp(session, org_id, opp_id)
    ds = _dataset(session, org_id)
    o.brief = opps.make_brief(o.snapshot, ds.cfg, _our_baseline(ds))
    if o.status == "saved":
        opps.record(o, "brief")
    session.add(o)
    session.commit()
    session.refresh(o)
    return _opp_out(o)


@app.patch("/organizations/{org_id}/opportunities/{opp_id}")
def update_opportunity(org_id: int, opp_id: int, data: OpportunityPatch, session: Session = Depends(get_session)):
    o = _opp(session, org_id, opp_id)
    sent = data.model_dump(exclude_unset=True)
    if "brief" in sent:
        o.brief = {**(o.brief or {}), **sent["brief"]}
    if "planned_for" in sent:
        o.planned_for = sent["planned_for"]
    if "mediaops_ref" in sent:
        o.mediaops_ref = (sent["mediaops_ref"] or "").strip() or None
    if "published_link" in sent:
        link = (sent["published_link"] or "").strip()
        if link and not link.lower().startswith(("http://", "https://")):
            raise HTTPException(400, "The published link must start with http:// or https://")
        o.published_link = link or None
        o.published_post_id = None
    status = sent.get("status")
    if status == "published" and not o.published_link:
        raise HTTPException(400, "Add the link of the published post first, so its results can be measured.")
    if status == "scheduled" and not o.planned_for:
        raise HTTPException(400, "Pick a date first.")
    if status:
        if status not in opps.TRANSITIONS:
            raise HTTPException(400, "Unknown status.")
        try:
            opps.record(o, status, sent.get("note"))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    o.updated_at = datetime.now(timezone.utc)
    session.add(o)
    session.commit()
    session.refresh(o)
    return _opp_out(o)


@app.post("/organizations/{org_id}/opportunities/{opp_id}/mediaops")
def send_to_mediaops(org_id: int, opp_id: int, data: MediaOpsIn, session: Session = Depends(get_session)):
    """Create a Draft Package in MediaOps (or return the text to paste). Never approves or publishes."""
    o = _opp(session, org_id, opp_id)
    org = _org(session, org_id)
    if o.mediaops_ref and o.status in ("in_mediaops", "scheduled", "published", "evaluated"):
        raise HTTPException(409, f"A MediaOps draft already exists for this opportunity ({o.mediaops_ref}). "
                                 "Open it in MediaOps instead of creating a second one.")
    if o.status in ("dismissed", "completed"):
        raise HTTPException(400, "Restore this opportunity before creating a draft.")
    if not o.brief:
        o.brief = opps.make_brief(o.snapshot, workspace.config(org), _our_baseline(_dataset(session, org_id)))
        if o.status == "saved":
            opps.record(o, "brief")
    payload = mediaops.draft_payload(o, org, data.platforms)
    if not mediaops.configured():
        session.add(o)
        session.commit()
        return {"mode": "copy", "text": opps.brief_text(o), "opportunity": _opp_out(o)}
    try:
        ref = mediaops.send_draft(payload, data.user_token)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(502, str(exc))
    o.mediaops_ref = ref or o.mediaops_ref
    opps.record(o, "in_mediaops", "Draft created in MediaOps")
    session.add(o)
    session.commit()
    session.refresh(o)
    return {"mode": "api", "ref": ref, "opportunity": _opp_out(o)}


@app.get("/organizations/{org_id}/opportunities/{opp_id}/calendar.ics")
def calendar_file(org_id: int, opp_id: int, session: Session = Depends(get_session)):
    o = _opp(session, org_id, opp_id)
    if not o.planned_for:
        raise HTTPException(400, "Pick a date first.")
    return Response(opps.ics(o), media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="opportunity-{o.id}.ics"'})


@app.post("/organizations/{org_id}/opportunities/{opp_id}/evaluate")
def evaluate_opportunity(org_id: int, opp_id: int, session: Session = Depends(get_session)):
    o = _opp(session, org_id, opp_id)
    if o.status not in ("published", "evaluated"):
        raise HTTPException(400, "Mark it as published (with the post link) first.")
    ds = _dataset(session, org_id)
    if not opps.match_published(session, o, list(ds.us_ids)) and not o.published_post_id:
        session.commit()
        return {"state": "not_found", "note": "We haven't collected this post yet. Make sure your own account is added as 'Ours', then click Refresh."}
    result = opps.evaluate(session, o, ds)
    o.outcome = result
    if result and result["state"] == "evaluated" and o.status == "published":
        opps.record(o, "evaluated", "Measured against your baseline.")
    session.add(o)
    session.commit()
    return result


# ---- Strategy experiments (and the strategy simulator) ----

class ExperimentIn(BaseModel):
    hypothesis: str = Field(min_length=5, max_length=400)
    reason: Optional[str] = Field(default=None, max_length=1000)
    evidence: dict = {}
    variable_type: Literal["format", "topic", "other"] = "other"
    variable_value: Optional[str] = Field(default=None, max_length=120)
    target_metric: str = "views_vs_usual"
    success_threshold: float = Field(default=1.2, gt=0)
    min_posts: int = Field(default=3, ge=1, le=50)
    duration_days: int = Field(default=28, ge=7, le=180)
    opportunity_id: Optional[int] = None


class ExperimentPatch(BaseModel):
    hypothesis: Optional[str] = Field(default=None, min_length=5, max_length=400)
    reason: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[str] = None
    success_threshold: Optional[float] = Field(default=None, gt=0)
    min_posts: Optional[int] = Field(default=None, ge=1, le=50)
    duration_days: Optional[int] = Field(default=None, ge=7, le=180)
    opportunity_id: Optional[int] = None
    add_post_link: Optional[str] = Field(default=None, max_length=500)
    remove_post_link: Optional[str] = Field(default=None, max_length=500)
    add_manual_result: Optional[dict] = None  # {link?, value, note?}
    remove_manual_result: Optional[int] = None  # index
    learning: Optional[str] = Field(default=None, max_length=2000)


def _exp(session, org_id, exp_id):
    e = session.get(Experiment, exp_id)
    if not e or e.org_id != org_id:
        raise HTTPException(404, "Experiment not found.")
    return e


def _exp_out(e):
    ends = utc(e.started_at) + timedelta(days=e.duration_days) if e.started_at else None
    return {**e.model_dump(), "started_at": iso(e.started_at), "ends_at": iso(ends), "created_at": iso(e.created_at),
            "updated_at": iso(e.updated_at), "metric": {"id": e.target_metric, **exps.TARGET_METRICS[e.target_metric]}}


def _check_link(link):
    link = (link or "").strip()
    if not link.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "The post link must start with http:// or https://")
    return opps.normalize_link(link)


@app.get("/organizations/{org_id}/experiments")
def list_experiments(org_id: int, session: Session = Depends(get_session)):
    """Your experiments, plus strategies the data suggests testing (the strategy simulator)."""
    ds, _, perf, recs = _analyse_all(session, org_id)
    rows = session.exec(select(Experiment).where(Experiment.org_id == org_id).order_by(Experiment.created_at.desc())).all()
    linked = {o.id: o for o in session.exec(select(Opportunity).where(Opportunity.org_id == org_id)).all()}
    return {
        "experiments": [{**_exp_out(e), "opportunity": ({"id": e.opportunity_id, "title": linked[e.opportunity_id].title,
                                                          "status": linked[e.opportunity_id].status}
                                                         if e.opportunity_id in linked else None)} for e in rows],
        "simulator": exps.strategies(ds, [r for r in recs if r["actionable"]]),
        "metrics": [{"id": k, **v} for k, v in exps.TARGET_METRICS.items()],
        "opportunities": [{"id": o.id, "title": o.title, "status": o.status} for o in linked.values()
                          if o.status not in ("dismissed",)],
    }


@app.post("/organizations/{org_id}/experiments", status_code=201)
def create_experiment(org_id: int, data: ExperimentIn, session: Session = Depends(get_session)):
    _org(session, org_id)
    if data.target_metric not in exps.TARGET_METRICS:
        raise HTTPException(400, "Choose a target metric from the list.")
    if data.opportunity_id:
        _opp(session, org_id, data.opportunity_id)
    e = Experiment(org_id=org_id, **{**data.model_dump(), "hypothesis": data.hypothesis.strip()})
    session.add(e)
    session.commit()
    session.refresh(e)
    return _exp_out(e)


EXPERIMENT_FLOW = {"planned": {"running", "cancelled"}, "running": {"completed", "cancelled", "planned"},
                   "completed": {"running"}, "cancelled": {"planned"}}


@app.patch("/organizations/{org_id}/experiments/{exp_id}")
def update_experiment(org_id: int, exp_id: int, data: ExperimentPatch, session: Session = Depends(get_session)):
    e = _exp(session, org_id, exp_id)
    sent = data.model_dump(exclude_unset=True)
    for k in ("hypothesis", "reason", "success_threshold", "min_posts", "duration_days", "learning"):
        if k in sent and sent[k] is not None:
            setattr(e, k, sent[k].strip() if isinstance(sent[k], str) else sent[k])
    if "opportunity_id" in sent:
        if sent["opportunity_id"]:
            _opp(session, org_id, sent["opportunity_id"])
        e.opportunity_id = sent["opportunity_id"]
    if sent.get("add_post_link"):
        link = _check_link(sent["add_post_link"])
        if link not in (e.post_links or []):
            e.post_links = [*(e.post_links or []), link]
    if sent.get("remove_post_link"):
        e.post_links = [x for x in (e.post_links or []) if x != sent["remove_post_link"]]
    if sent.get("add_manual_result") is not None:
        m = sent["add_manual_result"]
        try:
            value = float(m.get("value"))
        except (TypeError, ValueError):
            raise HTTPException(400, "Enter the result as a number.")
        link = _check_link(m["link"]) if m.get("link") else None
        e.manual_results = [*(e.manual_results or []), {"link": link, "value": value,
                                                         "note": (m.get("note") or "")[:300] or None,
                                                         "at": iso(datetime.now(timezone.utc))}]
    if sent.get("remove_manual_result") is not None:
        i = sent["remove_manual_result"]
        e.manual_results = [m for j, m in enumerate(e.manual_results or []) if j != i]
    status = sent.get("status")
    if status and status != e.status:
        if status not in EXPERIMENT_STATUSES or status not in EXPERIMENT_FLOW[e.status]:
            raise HTTPException(400, f'Can\'t move from "{e.status}" to "{status}".')
        if status == "running" and not e.started_at:
            e.started_at = datetime.now(timezone.utc)
        e.status = status
    e.updated_at = datetime.now(timezone.utc)
    session.add(e)
    session.commit()
    session.refresh(e)
    return _exp_out(e)


@app.post("/organizations/{org_id}/experiments/{exp_id}/evaluate")
def evaluate_experiment(org_id: int, exp_id: int, session: Session = Depends(get_session)):
    e = _exp(session, org_id, exp_id)
    if not e.post_links and not e.manual_results:
        raise HTTPException(400, "Add the links of the posts made for this experiment (or record results) first.")
    e.result = exps.evaluate(session, e, _dataset(session, org_id))
    e.updated_at = datetime.now(timezone.utc)
    session.add(e)
    session.commit()
    session.refresh(e)
    return _exp_out(e)


@app.delete("/organizations/{org_id}/experiments/{exp_id}", status_code=204)
def delete_experiment(org_id: int, exp_id: int, session: Session = Depends(get_session)):
    session.delete(_exp(session, org_id, exp_id))
    session.commit()
