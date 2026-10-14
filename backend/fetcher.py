"""Read every account of an organization through its platform connector and save new posts,
updated public metrics, timestamped snapshots (history) and audience questions."""
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

import connectors
import integrations
import social_http
import youtube
from models import AccountSnapshot, AudienceQuestion, Competitor, MetricSnapshot, Post

SNAPSHOT_EVERY = timedelta(hours=6)       # at most one metric snapshot per post per 6 hours
QUESTION_VIDEOS_PER_ACCOUNT = 3           # videos whose comments are read per account per refresh
QUESTION_RECHECK = timedelta(days=7)      # don't re-read the same video's comments for a week
QUESTION_MIN_BUDGET = 200                 # keep this many YouTube units for the next refresh
# A refresh reads each channel's latest videos. Busy channels (news) push older videos out of
# that list within a day or two, so their views would freeze. These settings re-check them.
METRICS_RECHECK_DAYS = 90                 # same period the "usual views" baseline uses
METRICS_RECHECK_MAX = 500                 # per account per refresh = at most 10 YouTube units


def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _save(session: Session, competitor: Competitor, items, now):
    """Insert new items; for items already saved, update metrics and metadata (they change over time)."""
    existing = {p.link: p for p in session.exec(select(Post).where(Post.competitor_id == competitor.id)).all()}
    last_snap = {}
    if existing:
        ids = [p.id for p in existing.values()]
        for snap in session.exec(select(MetricSnapshot).where(MetricSnapshot.post_id.in_(ids))).all():
            if snap.post_id not in last_snap or _utc(snap.captured_at) > _utc(last_snap[snap.post_id]):
                last_snap[snap.post_id] = snap.captured_at

    added, saved = 0, []
    for item in {i["link"]: i for i in items}.values():  # same link twice in one read
        post = existing.get(item["link"])
        if post:
            for field in ("views", "likes", "comments", "shares", "duration_seconds", "thumbnail", "tags", "format", "title"):
                if field in item:
                    setattr(post, field, item[field])
        else:
            post = Post(competitor_id=competitor.id, platform=competitor.platform, **item)
            added += 1
        if any(item.get(k) is not None for k in ("views", "likes", "comments")):
            post.metrics_updated_at = now
        session.add(post)
        saved.append(post)
    session.flush()  # gives new posts their ids

    snapshots = 0
    for post in saved:
        if post.views is None and post.likes is None and post.comments is None:
            continue  # nothing to record (e.g. RSS articles)
        last = last_snap.get(post.id)
        if last is None or now - _utc(last) >= SNAPSHOT_EVERY:
            session.add(MetricSnapshot(post_id=post.id, captured_at=now, views=post.views,
                                       likes=post.likes, comments=post.comments, shares=post.shares))
            snapshots += 1
    session.add(AccountSnapshot(competitor_id=competitor.id, captured_at=now,
                                subscribers=competitor.subscribers, posts_tracked=len(existing) + added))
    return added, snapshots


def _refresh_older_metrics(session, competitor, now):
    """Update views/likes/comments of saved YouTube videos that weren't in this refresh's latest batch."""
    if competitor.platform != "youtube" or youtube.budget_left() < QUESTION_MIN_BUDGET:
        return 0
    since = now - timedelta(days=METRICS_RECHECK_DAYS)
    stale = sorted(
        (p for p in session.exec(select(Post).where(Post.competitor_id == competitor.id)).all()
         if _utc(p.published_at) >= since and (p.metrics_updated_at is None or _utc(p.metrics_updated_at) < now)),
        key=lambda p: p.published_at, reverse=True,
    )[:METRICS_RECHECK_MAX]
    by_vid = {youtube.video_id(p.link): p for p in stale}
    by_vid.pop(None, None)
    if not by_vid:
        return 0
    stats = youtube.video_stats(list(by_vid))

    last_snap = {}
    for snap in session.exec(select(MetricSnapshot).where(MetricSnapshot.post_id.in_([p.id for p in by_vid.values()]))).all():
        if snap.post_id not in last_snap or _utc(snap.captured_at) > _utc(last_snap[snap.post_id]):
            last_snap[snap.post_id] = snap.captured_at
    for vid, st in stats.items():
        post = by_vid[vid]
        post.views, post.likes, post.comments = st["views"], st["likes"], st["comments"]
        post.metrics_updated_at = now
        session.add(post)
        last = last_snap.get(post.id)
        if last is None or now - _utc(last) >= SNAPSHOT_EVERY:
            session.add(MetricSnapshot(post_id=post.id, captured_at=now, **st))
    return len(stats)


def _collect_questions(session, connector, competitor, now):
    """Read comments on a few of the account's most-viewed recent videos and keep the questions."""
    if not connector.supports_questions or youtube.budget_left() < QUESTION_MIN_BUDGET:
        return 0
    since = now - timedelta(days=30)
    posts = session.exec(select(Post).where(Post.competitor_id == competitor.id)).all()
    candidates = sorted(
        (p for p in posts if _utc(p.published_at) >= since and (p.comments or 0) > 0
         and (p.questions_checked_at is None or now - _utc(p.questions_checked_at) >= QUESTION_RECHECK)),
        key=lambda p: p.views or 0, reverse=True,
    )[:QUESTION_VIDEOS_PER_ACCOUNT]
    found = 0
    for post in candidates:
        known = {q.comment_id for q in session.exec(select(AudienceQuestion).where(AudienceQuestion.post_id == post.id)).all()}
        for q in connector.questions(post):
            if q["comment_id"] not in known:
                session.add(AudienceQuestion(post_id=post.id, **q))
                found += 1
        post.questions_checked_at = now
        session.add(post)
    return found


def fetch_org(session: Session, org_id: int, now=None):
    """Read every account of one organization. One bad account doesn't stop the others.
    Instagram / Facebook / X accounts are skipped (no request made) until the platform is configured
    and connected for this workspace; an expired token or rate limit stops only that platform."""
    now = now or datetime.now(timezone.utc)
    results, added_total, quota_hit = [], 0, None
    accounts = session.exec(select(Competitor).where(Competitor.org_id == org_id)).all()
    contexts, stopped = {}, {}  # platform -> credentials; platform -> why it's stopped this refresh
    for c in accounts:
        try:
            connector = connectors.get(c.platform)
        except ValueError as exc:
            results.append({"account": c.name, "platform": c.platform, "added": 0, "error": str(exc)})
            continue
        ctx = None
        if getattr(connector, "requires_connection", False):
            if c.platform not in contexts:
                contexts[c.platform] = integrations.context(session, org_id, c.platform)
            ctx = contexts[c.platform]
            if ctx is None or c.platform in stopped:
                reason = stopped.get(c.platform) or integrations.not_ready_reason(session, org_id, c.platform)
                results.append({"account": c.name, "platform": c.platform, "added": 0, "error": None, "skipped": reason})
                continue
        try:
            items = connector.fetch(c, ctx) if ctx is not None else connector.fetch(c)
            added, snapshots = _save(session, c, items, now)
            questions = updated_older = 0
            if not quota_hit:
                try:
                    updated_older = _refresh_older_metrics(session, c, now)
                    questions = _collect_questions(session, connector, c, now)
                except youtube.QuotaExceeded as exc:
                    quota_hit = str(exc)  # posts are saved; only the optional comment check stops
            c.last_error = None
            c.last_fetched_at = now
            session.add(c)
            session.commit()
        except Exception as exc:
            session.rollback()
            if isinstance(exc, youtube.QuotaExceeded):
                quota_hit = str(exc)
            if isinstance(exc, social_http.TokenInvalid):
                conn = integrations.connection(session, org_id, c.platform)
                if conn:
                    integrations.mark_invalid(session, conn, str(exc))
                stopped[c.platform] = str(exc)
            elif isinstance(exc, social_http.RateLimited):
                stopped[c.platform] = str(exc)
            c.last_error = str(exc)[:300]
            session.add(c)
            session.commit()
            results.append({"account": c.name, "platform": c.platform, "added": 0, "error": c.last_error})
            continue
        results.append({"account": c.name, "platform": c.platform, "added": added, "found": len(items),
                        "snapshots": snapshots, "questions": questions, "updated_older": updated_older, "error": None})
        added_total += added
    return {
        "added": added_total,
        "accounts": results,
        "quota": {"youtube_units_used_today": youtube.units_used(), "youtube_units_left": youtube.budget_left(),
                  "warning": quota_hit},
    }
