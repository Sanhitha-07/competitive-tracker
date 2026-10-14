"""FastAPI app.

Options for forms:  /meta/options
Organizations:      /organizations, /organizations/{org_id}/config
Accounts per org:   /organizations/{org_id}/accounts
Fetch (Refresh):    /organizations/{org_id}/fetch
Results:            /organizations/{org_id}/results (everything the dashboard needs), /overview, /gaps,
                    /speed, /performance, /topics, /recommendations
Content Explorer:   /organizations/{org_id}/content
History:            /organizations/{org_id}/history, /organizations/{org_id}/posts/{post_id}/history
Opportunities:      /organizations/{org_id}/opportunities (+ /{opp_id}, /brief, /mediaops, /calendar.ics, /evaluate)
Dashboard:          /organizations/{org_id}/dashboard (+ POST /briefing/ai for the optional AI briefing)
Trends:             /organizations/{org_id}/trends (+ POST /trends/refresh)

    run_api.bat      then open http://localhost:8000/docs
"""
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import Session, delete, select

import ai
import config
import connectors
import insights
import mediaops
import meta
import opportunities as opps
import recommend
import trends
import workspace
import youtube
from analysis import analyse
from dataset import Dataset, iso, utc
from db import create_tables, get_session
from fetcher import fetch_org
from models import (AccountSnapshot, AudienceQuestion, Competitor, MetricSnapshot, Opportunity,
                    Organization, Post, TrendItem)
from performance import compare
from topics import STATUS_LABELS

app = FastAPI(title="MediaOps Competitive Tracker")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    create_tables()


@app.get("/meta/options")
def meta_options():
    """Choices for the workspace form and what each platform can measure."""
    return {**workspace.options(), "platforms": connectors.describe(),
            "youtube_quota": {"used_today": youtube.units_used(), "left": youtube.budget_left()},
            "integrations": {
                "youtube": bool(youtube.YOUTUBE_API_KEY),
                "meta": meta.configured(),
                "ai": ai.configured(),
                "trends": {"google_trends": config.TRENDS_GOOGLE_TRENDS, "google_news": config.TRENDS_GOOGLE_NEWS,
                           "youtube_trending": bool(youtube.YOUTUBE_API_KEY)},
            },
            "mediaops_api": mediaops.configured()}


# ---- Organizations (workspaces) ----

class WorkspaceIn(BaseModel):
    creator_type: Optional[str] = None
    category: Optional[str] = None  # industry id
    niche: Optional[str] = Field(default=None, max_length=120)
    audience: Optional[str] = Field(default=None, max_length=300)
    goals: Optional[list[str]] = None
    topics: Optional[list[str]] = None
    formats: Optional[list[str]] = None
    platforms: Optional[list[str]] = None
    timezone: Optional[str] = None
    time_sensitive: Optional[bool] = None
    window_hours: Optional[int] = None
    region: Optional[str] = None
    brand_safety: Optional[str] = None


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
    for k in ("niche", "audience"):
        if k in sent and sent[k] is not None:
            sent[k] = sent[k].strip() or None
    for k, v in sent.items():
        if k != "name" and (v is not None or k in ("niche", "audience", "creator_type", "time_sensitive", "brand_safety")):
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
    session.exec(delete(Opportunity).where(Opportunity.org_id == org_id))
    session.exec(delete(TrendItem).where(TrendItem.org_id == org_id))
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
    session.exec(delete(AccountSnapshot).where(AccountSnapshot.competitor_id == account_id))
    session.exec(delete(Post).where(Post.competitor_id == account_id))


# ---- Accounts (ours and competitors') ----

class AccountIn(BaseModel):
    name: str
    platform: str = "rss"
    source: str
    is_us: bool = False


@app.get("/organizations/{org_id}/accounts")
def list_accounts(org_id: int, session: Session = Depends(get_session)):
    _org(session, org_id)
    accounts = session.exec(
        select(Competitor).where(Competitor.org_id == org_id)
        .order_by(Competitor.is_us.desc(), Competitor.name, Competitor.platform)
    ).all()
    # SQLite drops the time zone; send UTC explicitly so browsers don't read it as local time.
    return [{**a.model_dump(), "last_fetched_at": iso(a.last_fetched_at)} for a in accounts]


@app.post("/organizations/{org_id}/accounts", status_code=201)
def add_account(org_id: int, data: AccountIn, session: Session = Depends(get_session)):
    _org(session, org_id)
    name, source = data.name.strip(), data.source.strip()
    if not name or not source:
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

    account = Competitor(org_id=org_id, name=name, platform=data.platform, source=source, is_us=data.is_us)
    try:
        found = connector.resolve(source)  # check the account exists before saving
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    for k, v in found.items():
        setattr(account, k, v)
    if account.channel_id:
        duplicate = session.exec(same_org.where(Competitor.channel_id == account.channel_id)).first()
    else:
        duplicate = session.exec(same_org.where(Competitor.source == source)).first()
    if duplicate:
        raise HTTPException(400, f"This {_label(data.platform)} is already added as \"{duplicate.name}\".")

    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@app.delete("/organizations/{org_id}/accounts/{account_id}", status_code=204)
def remove_account(org_id: int, account_id: int, session: Session = Depends(get_session)):
    account = session.get(Competitor, account_id)
    if not account or account.org_id != org_id:
        raise HTTPException(404, "Account not found.")
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


def _label(platform):
    return {"youtube": "YouTube channel", "instagram": "Instagram account", "facebook": "Facebook Page"}.get(platform, "RSS feed")


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


def _dataset(session, org_id, now=None):
    org, accounts, posts = _load(session, org_id)
    post_ids = [p.id for p in posts]
    questions = session.exec(select(AudienceQuestion).where(AudienceQuestion.post_id.in_(post_ids))).all() if post_ids else []
    return Dataset(org, accounts, posts, questions, now)


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


def _topic_rows(ds):
    rows, our_total = ds.topics()
    out = []
    for t in rows:
        out.append({**{k: v for k, v in t.items() if k != "post_ids"},
                    "latest": iso(t["latest"]), "status_label": STATUS_LABELS[t["status"]],
                    "posts": len(t["post_ids"])})
    return out, our_total


@app.get("/organizations/{org_id}/results")
def results(org_id: int, session: Session = Depends(get_session)):
    """Everything the dashboard needs in one call."""
    ds, news, perf, recs = _analyse_all(session, org_id)
    topic_rows, _ = _topic_rows(ds)
    to_review = sum(1 for t in topic_rows if t["status"] in ("not_covered_by_you", "covered_less") and t["competitor_posts"] >= 2)
    overview = {**news["overview"], "topics_to_review": to_review, "questions": len(ds.questions)}
    return {"organization": ds.org, "config": ds.cfg, **news, "overview": overview, "performance": perf,
            "recommendations": recs, "readiness": recommend.readiness(ds, perf),
            "period": ds.period(), "freshness": ds.freshness()}


@app.get("/organizations/{org_id}/dashboard")
def dashboard(org_id: int, session: Session = Depends(get_session)):
    """The Dashboard: plain-language briefing, KPIs and chart data for the period."""
    ds, _, perf, recs, trend_items = _analyse_all(session, org_id, with_trends=True)
    ids = [a.id for a in ds.accounts]
    snaps = {}
    if ids:
        for sn in session.exec(select(AccountSnapshot).where(AccountSnapshot.competitor_id.in_(ids))).all():
            snaps.setdefault(sn.competitor_id, []).append(sn)
    return {**insights.build(ds, perf, recs, trend_items, snaps), "config": ds.cfg, "ai_available": ai.configured()}


@app.post("/organizations/{org_id}/briefing/ai")
def ai_briefing(org_id: int, session: Session = Depends(get_session)):
    """Optional: Claude rewrites the briefing and suggests content ideas from the dashboard numbers."""
    data = dashboard(org_id, session)
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
def get_topics(org_id: int, session: Session = Depends(get_session)):
    """Topic coverage map for the comparison period."""
    ds = _dataset(session, org_id)
    rows, our_total = _topic_rows(ds)
    return {"topics": rows, "your_posts_checked": our_total, "competitor_posts_checked": len([p for p in ds.recent if not ds.is_us(p)]),
            "period": ds.period(), "freshness": ds.freshness(), "status_labels": STATUS_LABELS,
            "method": "Topics are words, two-word phrases and creator tags shared by several accounts, plus your workspace topics. Matching is by keywords, so different wording for the same idea isn't joined."}


@app.get("/organizations/{org_id}/recommendations")
def get_recommendations(org_id: int, session: Session = Depends(get_session)):
    ds, _, perf, recs = _analyse_all(session, org_id)
    return {"recommendations": recs, "readiness": recommend.readiness(ds, perf)}


# ---- Content Explorer ----

PERF_FILTERS = {"outlier": (2.0, None), "above": (1.2, None), "usual": (0.8, 1.2), "below": (None, 0.8)}


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
    sort: Literal["newest", "views", "relative"] = "newest",
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    """Searchable gallery of collected posts (competitors', and ours if asked)."""
    ds = _dataset(session, org_id)
    topic_rows, _ = ds.topics()
    topics_of = {}
    for t in topic_rows:
        for pid in t["post_ids"]:
            topics_of.setdefault(pid, []).append(t["topic"])
    tracked = [t.lower() for t in ds.cfg["topics"]]

    items = [p for p in ds.posts if include_ours or not ds.is_us(p)]
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
        if not tracked:
            raise HTTPException(400, "Add topics in Workspace settings to use this filter.")
        items = [p for p in items if any(t in (p.title + " " + " ".join(p.tags or [])).lower() for t in tracked)]
    if q:
        ql = q.lower()
        items = [p for p in items if ql in p.title.lower() or any(ql in x.lower() for x in (p.tags or []))]
    if performance == "unknown":
        items = [p for p in items if ds.relative.get(p.id) is None]
    elif performance:
        lo, hi = PERF_FILTERS[performance]
        items = [p for p in items if ds.relative.get(p.id) is not None
                 and (lo is None or ds.relative[p.id] >= lo) and (hi is None or ds.relative[p.id] < hi)]

    key = {"newest": lambda p: utc(p.published_at), "views": lambda p: connectors.metric_value(p) or -1,
           "relative": lambda p: ds.relative.get(p.id) or -1}[sort]
    items.sort(key=key, reverse=True)
    page = items[offset:offset + limit]
    return {
        "total": len(items),
        "items": [{**ds.post_card(p), "topics": topics_of.get(p.id, [])[:6], "tags": (p.tags or [])[:8]} for p in page],
        "facets": {
            "accounts": [{"id": a.id, "name": a.name, "platform": a.platform, "is_us": a.is_us} for a in ds.accounts],
            "platforms": sorted({a.platform for a in ds.accounts}),
            "formats": sorted({ds.format(p) for p in ds.posts if ds.format(p)}),
            "topics": [t["topic"] for t in topic_rows[:40]],
            "my_topics": ds.cfg["topics"],
        },
        "definitions": {"relative": "A post's views (YouTube) or interactions (Instagram, Facebook) ÷ the same account's median (posts 48h+ old, last 90 days). Blank when the platform has no public numbers or the account has fewer than 5 such posts."},
        "freshness": ds.freshness(),
    }


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
            views = sorted(connectors.metric_value(p) for p in ps if connectors.metric_value(p) is not None)
            rel = sorted(ds.relative[p.id] for p in ps if ds.relative.get(p.id) is not None)
            weekly.append({"week": w, "posts": len(ps), "median_views": views[len(views) // 2] if views else None,
                           "median_relative": rel[len(rel) // 2] if rel else None})
        growth = None
        if len(audience) >= 2 and audience[0]["subscribers"]:
            first, last = audience[0], audience[-1]
            growth = {"from": first["subscribers"], "to": last["subscribers"],
                      "change": last["subscribers"] - first["subscribers"], "since": first["at"]}
        out.append({"id": a.id, "name": a.name, "platform": a.platform, "is_us": a.is_us,
                    "metric": connectors.performance_metric(a.platform), "audience_label": connectors.audience_label(a.platform),
                    "audience": audience, "audience_growth": growth, "weekly": weekly,
                    "baseline": ds.baseline.get(a.id)})
    our_recent = sorted((p for p in ds.posts if ds.is_us(p) and utc(p.published_at) >= ds.now - timedelta(days=30)),
                        key=lambda p: p.published_at, reverse=True)
    return {
        "days": days, "accounts": out,
        "our_recent_vs_baseline": [ds.post_card(p) for p in our_recent[:15]],
        "notes": ["Audience numbers are saved each time you click Refresh, so the history starts from your first refresh.",
                  "YouTube rounds subscriber counts, so small changes may not show.",
                  "Weekly medians use views on YouTube and interactions (likes + comments + shares) on Instagram and Facebook, from each post's latest numbers. Older weeks have had more time to collect them."],
    }


@app.get("/organizations/{org_id}/posts/{post_id}/history")
def post_history(org_id: int, post_id: int, session: Session = Depends(get_session)):
    post = session.get(Post, post_id)
    account = session.get(Competitor, post.competitor_id) if post else None
    if not post or not account or account.org_id != org_id:
        raise HTTPException(404, "Post not found.")
    snaps = session.exec(select(MetricSnapshot).where(MetricSnapshot.post_id == post_id).order_by(MetricSnapshot.captured_at)).all()
    return {"post": {"id": post.id, "title": post.title, "link": post.link, "published_at": iso(post.published_at)},
            "snapshots": [{"at": iso(s.captured_at), "views": s.views, "likes": s.likes, "comments": s.comments,
                           "shares": s.shares} for s in snaps]}


# ---- Opportunities ----

class OpportunityIn(BaseModel):
    key: str
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
        "suggested": [r for r in recs if r["actionable"] and r["key"] not in taken],
        "tracked": [_opp_out(o) for o in tracked],
        "learned": opps.learned_stats(session, org_id),
        "mediaops_api": mediaops.configured(),
        "readiness": recommend.readiness(ds, perf),
        "eval_after_days": opps.EVAL_AFTER_DAYS,
    }


@app.post("/organizations/{org_id}/opportunities", status_code=201)
def create_opportunity(org_id: int, data: OpportunityIn, session: Session = Depends(get_session)):
    existing = session.exec(select(Opportunity).where(Opportunity.org_id == org_id, Opportunity.key == data.key)).first()
    if existing and existing.status != "dismissed":
        return _opp_out(existing)
    ds, _, _, recs = _analyse_all(session, org_id)
    rec = next((r for r in recs if r["key"] == data.key), None)
    if not rec:
        raise HTTPException(404, "This recommendation is no longer in the data. Click Refresh and try again.")
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
