"""Read every account of an organization (RSS feeds and YouTube channels) and save new stories/videos."""
import calendar
from datetime import datetime, timezone

import feedparser
from sqlmodel import Session, select

import youtube
from models import Competitor, Post


def read_feed(rss_url):
    """Return a list of {title, link, published_at} from one RSS feed. Raises ValueError if it isn't a feed."""
    feed = feedparser.parse(rss_url, agent="Mozilla/5.0 CompetitiveTracker")
    if not feed.entries:
        reason = getattr(feed, "bozo_exception", None)
        raise ValueError(f"No stories found. Is this an RSS feed link? {reason or ''}".strip())
    stories = []
    for e in feed.entries:
        if not e.get("title") or not e.get("link"):
            continue
        t = e.get("published_parsed") or e.get("updated_parsed")
        # Always UTC, with timezone info (the database requires it).
        when = datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc) if t else datetime.now(timezone.utc)
        stories.append({"title": e.title.strip(), "link": e.link, "published_at": when})
    return stories


def read_youtube(competitor: Competitor):
    channel = youtube.find_channel(competitor.channel_id or competitor.source)
    competitor.channel_id = channel["channel_id"]
    competitor.subscribers = channel["subscribers"]
    competitor.thumbnail = channel["thumbnail"]
    return youtube.latest_videos(channel["uploads_playlist"])


def _save(session: Session, competitor: Competitor, items):
    """Insert new items; for videos already saved, update views/likes/comments (they change over time)."""
    existing = {p.link: p for p in session.exec(select(Post).where(Post.competitor_id == competitor.id)).all()}
    added = 0
    for item in {i["link"]: i for i in items}.values():  # same link twice in one read
        old = existing.get(item["link"])
        if old:
            if competitor.platform == "youtube":
                old.views, old.likes, old.comments = item["views"], item["likes"], item["comments"]
                session.add(old)
            continue
        session.add(Post(competitor_id=competitor.id, platform=competitor.platform, **item))
        added += 1
    return added


def fetch_org(session: Session, org_id: int):
    """Read every account of one organization. One bad account doesn't stop the others."""
    results, added_total = [], 0
    accounts = session.exec(select(Competitor).where(Competitor.org_id == org_id)).all()
    for c in accounts:
        try:
            items = read_youtube(c) if c.platform == "youtube" else read_feed(c.source)
            added = _save(session, c, items)
            c.last_error = None
            session.add(c)
            session.commit()
        except Exception as exc:
            session.rollback()
            c.last_error = str(exc)[:300]
            session.add(c)
            session.commit()
            results.append({"account": c.name, "platform": c.platform, "added": 0, "error": c.last_error})
            continue
        results.append({"account": c.name, "platform": c.platform, "added": added, "found": len(items), "error": None})
        added_total += added
    return {"added": added_total, "accounts": results}
