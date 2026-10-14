"""What's trending on the internet that relates to a workspace, and what to do about it.

Sources (each can fail on its own without stopping the others):
  google_trends     Google's "Trending now" daily searches for the workspace's country (RSS).
                    Kept when it matches the workspace; news organisations see all of them.
  google_news       Google News search for each workspace topic over the last 7 days (RSS):
                    how much is being published about it, and whether that's rising.
                    For personal/non-commercial use under Google's terms: TRENDS_GOOGLE_NEWS=0 turns it off.
  youtube_trending  YouTube's official Trending chart for the country and the industry's video category.

Relevance is keyword matching against the workspace's topics, niche, audience, industry and the
topics its competitors post about. Every trend is rated for sensitivity (sensitivity.py) and
compared with what the tracked accounts already posted, so a suggestion can say "2 competitors
already covered this; you haven't" or "no one you track has covered it yet".
"""
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from sqlmodel import Session, delete, select

import config
import sensitivity
import textutil
import workspace
import youtube
from dataset import iso, utc
from models import TrendItem
from topics import STOPWORDS

CACHE_MINUTES = 60          # don't re-read the same sources more often than this
KEEP_DAYS = 7               # older trend rows are deleted
MAX_NEWS_QUERIES = 6        # Google News searches per refresh
RECENT_HOURS = 48           # "recent" part of the momentum ratio
RISING = 1.5                # momentum at or above this = "rising"
HT = "{https://trends.google.com/trending/rss}"
UA = "Mozilla/5.0 CompetitiveTracker"


# ---- reading the sources ----

def _http(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.read()
    except urllib.error.URLError as exc:
        raise ValueError(f"Can't reach {urllib.parse.urlparse(url).netloc}: {getattr(exc, 'reason', exc)}") from exc


def _date(text):
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_google_trends(xml_bytes):
    """[{title, traffic, published_at, picture, news: [{title, link, source}]}]"""
    root = ET.fromstring(xml_bytes)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        news = [{"title": (n.findtext(f"{HT}news_item_title") or "").strip(),
                 "link": n.findtext(f"{HT}news_item_url"),
                 "source": n.findtext(f"{HT}news_item_source")}
                for n in item.findall(f"{HT}news_item")]
        out.append({"title": title, "traffic": item.findtext(f"{HT}approx_traffic"),
                    "published_at": _date(item.findtext("pubDate")), "picture": item.findtext(f"{HT}picture"),
                    "news": [n for n in news if n["title"]]})
    return out


def parse_google_news(xml_bytes):
    """[{title, link, source, published_at}] -- Google appends " - Source" to titles; it's split off."""
    root = ET.fromstring(xml_bytes)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        source = (item.findtext("source") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        if title:
            out.append({"title": title, "link": item.findtext("link"), "source": source or None,
                        "published_at": _date(item.findtext("pubDate"))})
    return out


def google_trends(region):
    return parse_google_trends(_http(f"https://trends.google.com/trending/rss?geo={region}"))


def google_news(query, region, days=7):
    lang = "en"
    q = urllib.parse.quote(f'"{query}" when:{days}d')
    url = f"https://news.google.com/rss/search?q={q}&hl={lang}-{region}&gl={region}&ceid={region}:{lang}"
    return parse_google_news(_http(url))


def momentum(items, now):
    """Articles per day in the last 48 hours ÷ articles per day in the 5 days before.
    Above 1 = more coverage now than before. None when there's too little to tell."""
    recent = sum(1 for i in items if i["published_at"] and now - i["published_at"] <= timedelta(hours=RECENT_HOURS))
    earlier = sum(1 for i in items if i["published_at"] and timedelta(hours=RECENT_HOURS) < now - i["published_at"] <= timedelta(days=7))
    if recent + earlier < 4:
        return None
    return round((recent / 2) / max(earlier / 5, 0.2), 2)


# ---- what the workspace cares about ----

def _content_words(text):
    return [w for w in textutil.words(text) if len(w) >= 3 and w not in STOPWORDS]


def keywords(cfg, competitor_topics=()):
    """[(term, weight, why)] most specific first: your topics, then niche/audience, competitors' topics, industry."""
    out, seen = [], set()

    def add(term, weight, why):
        t = " ".join(textutil.words(term))
        if t and t not in seen and len(t) >= 3:
            seen.add(t)
            out.append((t, weight, why))

    for t in cfg["topics"]:
        add(t, 3.0, f'your workspace topic "{t}"')
    if cfg["niche"]:
        add(cfg["niche"], 2.5, "your niche")
        for w in _content_words(cfg["niche"]):
            add(w, 1.6, "your niche")
    for w in _content_words(cfg["audience"]):
        add(w, 1.0, "your audience")
    for t in list(competitor_topics)[:15]:
        add(t, 1.4, f'"{t}", a topic your competitors post about')
    for w in workspace.INDUSTRY_KEYWORDS.get(cfg["industry"], "").split():
        add(w, 1.0, f"the {cfg['industry_label'].lower()} industry")
    return out


def relevance(text, terms):
    """(score, matched terms, the strongest reason). 0 when nothing matches."""
    low = text.lower()
    hits = [(t, w, why) for t, w, why in terms if textutil.contains_phrase(low, t)]
    if not hits:
        return 0.0, [], None
    hits.sort(key=lambda h: -h[1])
    score = hits[0][1] + 0.3 * sum(h[1] for h in hits[1:4])
    return round(score, 2), [h[0] for h in hits[:5]], hits[0][2]


def _queries(cfg, competitor_topics):
    """What to search Google News for: your topics first, then your niche, then competitors' topics."""
    qs = list(cfg["topics"])
    if cfg["niche"]:
        qs.append(cfg["niche"])
    qs += [t for t in competitor_topics if " " in t]  # two-word topics make specific searches
    seen, out = set(), []
    for q in qs:
        k = q.lower().strip()
        if k and k not in seen:
            seen.add(k)
            out.append(q.strip())
    return out[:MAX_NEWS_QUERIES]


# ---- refresh: read sources and save matches ----

def _key(source, title):
    return f"{source}:{' '.join(textutil.words(title))[:180]}"


def last_refresh(session, org_id):
    row = session.exec(select(TrendItem).where(TrendItem.org_id == org_id).order_by(TrendItem.fetched_at.desc())).first()
    return utc(row.fetched_at) if row else None


def refresh(session: Session, org, competitor_topics=(), force=False, now=None):
    """Read every enabled source for this workspace and save what's relevant. Returns a summary."""
    now = now or datetime.now(timezone.utc)
    last = last_refresh(session, org.id)
    if not force and last and now - last < timedelta(minutes=CACHE_MINUTES):
        return {"skipped": True, "last_refresh": iso(last), "sources": []}
    cfg = workspace.config(org)
    region = cfg["region"]
    terms = keywords(cfg, competitor_topics)
    found, sources = [], []

    if config.TRENDS_GOOGLE_TRENDS:
        try:
            items = google_trends(region)
            kept = 0
            for t in items:
                text = " ".join([t["title"], *(n["title"] for n in t["news"])])
                score, _, _ = relevance(text, terms)
                if score > 0 or cfg["is_news"]:
                    kept += 1
                    found.append(TrendItem(org_id=org.id, key=_key("google_trends", t["title"]), source="google_trends",
                                           title=t["title"], link=(t["news"][0]["link"] if t["news"] else None),
                                           traffic=t["traffic"], picture=t["picture"], published_at=t["published_at"],
                                           fetched_at=now, related=[{**n, "published_at": None} for n in t["news"][:5]]))
            sources.append({"source": "google_trends", "ok": True, "read": len(items), "kept": kept})
        except (ValueError, ET.ParseError) as exc:
            sources.append({"source": "google_trends", "ok": False, "error": str(exc)[:200]})

    if config.TRENDS_GOOGLE_NEWS:
        queries = _queries(cfg, competitor_topics)
        ok = 0
        errors = []
        for q in queries:
            try:
                arts = google_news(q, region)
            except (ValueError, ET.ParseError) as exc:
                errors.append(str(exc)[:120])
                continue
            ok += 1
            if not arts:
                continue
            arts.sort(key=lambda a: a["published_at"] or now - timedelta(days=30), reverse=True)
            found.append(TrendItem(org_id=org.id, key=_key("google_news", q), source="google_news", title=q, query=q,
                                   link=arts[0]["link"], volume=len(arts), momentum=momentum(arts, now),
                                   published_at=arts[0]["published_at"], fetched_at=now,
                                   related=[{**a, "published_at": iso(a["published_at"])} for a in arts[:6]]))
        if queries:
            sources.append({"source": "google_news", "ok": ok > 0 or not errors, "read": ok, "kept": ok,
                            **({"error": errors[0]} if errors and not ok else {})})

    if youtube.YOUTUBE_API_KEY and youtube.budget_left() > 50:
        category = workspace.YOUTUBE_CATEGORY.get(cfg["industry"])
        try:
            try:
                vids = youtube.trending_videos(region, category)
            except ValueError:
                if not category:
                    raise
                vids = youtube.trending_videos(region)  # not every category has a chart in every country
                category = None
            kept = 0
            for v in vids:
                score, _, _ = relevance(" ".join([v["title"], *v["tags"]]), terms)
                if score > 0 or category or cfg["is_news"]:
                    kept += 1
                    found.append(TrendItem(org_id=org.id, key=_key("youtube_trending", v["title"]), source="youtube_trending",
                                           title=v["title"], link=v["link"], summary=v["channel"], volume=v["views"],
                                           picture=v["thumbnail"], published_at=v["published_at"], fetched_at=now,
                                           related=[]))
            sources.append({"source": "youtube_trending", "ok": True, "read": len(vids), "kept": kept})
        except ValueError as exc:
            sources.append({"source": "youtube_trending", "ok": False, "error": str(exc)[:200]})

    # Replace what this refresh re-read; keep older items for a week so "still trending" can be seen.
    session.exec(delete(TrendItem).where(TrendItem.org_id == org.id, TrendItem.fetched_at < now - timedelta(days=KEEP_DAYS)))
    existing = {t.key: t for t in session.exec(select(TrendItem).where(TrendItem.org_id == org.id)).all()}
    for item in {i.key: i for i in found}.values():
        old = existing.get(item.key)
        if old:
            for f in ("title", "link", "traffic", "volume", "momentum", "picture", "published_at", "related", "summary"):
                setattr(old, f, getattr(item, f))
            old.fetched_at = now
            session.add(old)
        else:
            session.add(item)
    session.commit()
    return {"skipped": False, "last_refresh": iso(now), "sources": sources, "saved": len(found)}


# ---- turn saved trends into explained, workspace-specific items ----

def _coverage(ds, trend_title, since):
    """Tracked posts since `since` that mention the trend: (yours, competitors' names, matching posts)."""
    words = [w for w in _content_words(trend_title)]
    if not words:
        return [], [], []
    need = 1 if len(words) == 1 else 2
    ours, theirs, posts = [], set(), []
    for p in ds.posts:
        if utc(p.published_at) < since:
            continue
        text = " ".join([p.title, *(getattr(p, "tags", None) or [])])
        if textutil.contains_phrase(text, trend_title) or sum(1 for w in set(words) if w in set(textutil.words(text))) >= need:
            posts.append(p)
            if ds.is_us(p):
                ours.append(p)
            else:
                theirs.add(ds.by_id[p.competitor_id].name)
    return ours, sorted(theirs), posts


ANGLES = {
    "news": ["Explainer: what happened and what it means for your {audience}",
             "Timeline / live updates as the story develops",
             "Fact-check: what's confirmed and what isn't yet"],
    "business": ["A genuinely useful tip for your customers connected to \"{trend}\"",
                 "Show how your product or service fits, only if the link is natural",
                 "A timely offer or post, only for festive, seasonal or fun trends"],
    "creator": ["Your take on \"{trend}\" from your {niche} experience",
                "How-to or tutorial linked to \"{trend}\"",
                "Myths vs facts about \"{trend}\" for your {audience}"],
}


def _angles(cfg, title):
    kind = "news" if cfg["is_news"] else "business" if cfg["is_business"] else "creator"
    audience = cfg["audience"] or ("viewers" if kind == "news" else "audience")
    niche = cfg["niche"] or cfg["industry_label"].lower()
    return [a.format(trend=title, audience=audience, niche=niche) for a in ANGLES[kind]]


# The only angle offered for a sensitive topic outside a newsroom: no hot takes, no humour, no promotion.
CAREFUL_ANGLE = ("Only if it truly relates to your field: a calm, factual explainer from your own expertise, "
                 "pointing to reliable sources. No speculation, jokes, clickbait or promotion.")

SOURCE_LABEL = {"google_trends": "Google Trends (searches)", "google_news": "In the news",
                "youtube_trending": "YouTube Trending"}


def build(ds, rows, competitor_topics=()):
    """Saved trend rows -> explained items, most relevant first."""
    cfg = ds.cfg
    terms = keywords(cfg, competitor_topics)
    safety = cfg["brand_safety"]
    since = ds.now - timedelta(days=7)
    out = []
    for r in rows:
        related_titles = [x.get("title", "") for x in (r.related or [])]
        text = " ".join([r.title, *related_titles[:3]])
        score, matched, why = relevance(text, terms)
        if r.query:  # a search for one of the workspace's own topics
            score, why = max(score, 3.0), f'your topic "{r.query}"' if r.query in cfg["topics"] else why or f'"{r.query}"'
        if score == 0 and not cfg["is_news"] and r.source != "youtube_trending":
            continue
        sens = sensitivity.classify(r.title, *related_titles[:3])
        adv = sensitivity.advice(sens["level"], safety)
        ours, theirs, posts = _coverage(ds, r.title, since)
        rising = r.momentum is not None and r.momentum >= RISING
        freshness_h = (ds.now - utc(r.published_at)).total_seconds() / 3600 if r.published_at else None
        recency = 1.3 if freshness_h is not None and freshness_h <= 24 else 1.0
        rank = (score or 0.5) * recency * (1.3 if rising else 1.0) * (1.2 if theirs and not ours else 1.0)
        if adv["action"] == "avoid":
            rank *= 0.4
        if theirs and not ours:
            coverage = f"{len(theirs)} competitor{'s' if len(theirs) != 1 else ''} you track posted about it this week ({', '.join(theirs[:3])}); you haven't."
        elif ours:
            coverage = f"You've already posted about it ({len(ours)} post{'s' if len(ours) != 1 else ''} this week)" + (f", as did {', '.join(theirs[:3])}." if theirs else ".")
        else:
            coverage = "No account you track has posted about it in the last 7 days: a chance to be early."
        signal = {"google_trends": f"{r.traffic or 'Many'} Google searches in {cfg['region_label']}",
                  "google_news": f"{r.volume} news articles in 7 days" + (f", rising {r.momentum}×" if rising else (f" ({r.momentum}× the earlier rate)" if r.momentum else "")),
                  "youtube_trending": f"On YouTube Trending ({cfg['region_label']})" + (f" with {r.volume:,} views" if r.volume else "")}[r.source]
        out.append({
            "id": r.id, "key": f"trend:{r.key}", "source": r.source, "source_label": SOURCE_LABEL[r.source],
            "title": r.title, "link": r.link, "picture": r.picture, "summary": r.summary,
            "traffic": r.traffic, "volume": r.volume, "momentum": r.momentum, "rising": rising,
            "published_at": iso(r.published_at), "fetched_at": iso(r.fetched_at),
            "signal": signal,
            "relevance": score, "matched": matched,
            "why_relevant": f"Matches {why}." if why else ("Top search in your country; shown to news organisations." if cfg["is_news"] else "In your industry's YouTube Trending category."),
            "sensitivity": sens, "advice": adv,
            "coverage": {"text": coverage, "yours": len(ours), "competitors": theirs,
                         "posts": [ds.post_card(p) for p in sorted(posts, key=lambda p: p.published_at, reverse=True)[:4]]},
            "angles": _angles(cfg, r.title) if adv["action"] == "go" or (adv["action"] == "care" and safety == "newsroom")
                      else [CAREFUL_ANGLE] if adv["action"] == "care" else [],
            "related": (r.related or [])[:5],
            "rank": round(rank, 3),
        })
    out.sort(key=lambda t: -t["rank"])
    # The same trend from two sources (e.g. Google searches and news) is shown once, with both signals.
    merged, by_title = [], {}
    for t in out:
        k = " ".join(textutil.words(t["title"]))
        if k in by_title:
            first = by_title[k]
            first["signal"] += " · " + t["signal"]
            first["rising"] = first["rising"] or t["rising"]
            first["momentum"] = first["momentum"] or t["momentum"]
            first["related"] = (first["related"] + t["related"])[:6]
            first.setdefault("also_from", []).append(t["source_label"])
            continue
        by_title[k] = t
        merged.append(t)
    return merged


def load(session, ds, competitor_topics=()):
    rows = session.exec(select(TrendItem).where(TrendItem.org_id == ds.org.id)).all()
    return build(ds, rows, competitor_topics)


def competitor_topics(ds):
    """The topics competitors post about most (from the coverage map), to widen trend matching."""
    rows, _ = ds.topics()
    return [t["topic"] for t in rows if t["competitor_posts"] >= 2][:20]
