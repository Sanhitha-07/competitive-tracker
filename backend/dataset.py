"""Everything one analysis needs, computed once per request: the workspace configuration,
the comparison period, each account's baseline and each post's relative performance.

Baseline = the median views of an account's posts that are at least 48 hours old,
from the last 90 days. A post's relative performance = its views ÷ its own account's baseline,
so a small creator and a large brand can be compared fairly.
"""
from datetime import datetime, timedelta, timezone
from statistics import median

import topics as topic_map
import workspace
from connectors import YouTubeConnector

BASELINE_DAYS = 90
BASELINE_MIN_AGE = timedelta(hours=48)
BASELINE_MIN_POSTS = 5
OUTLIER_RATIO = 2.0  # 2× the account's usual views


def utc(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def iso(dt):
    return utc(dt).isoformat() if dt else None


class Dataset:
    def __init__(self, org, accounts, posts, questions=(), now=None):
        self.org = org
        self.cfg = workspace.config(org)
        self.tz = workspace.tz(org)
        self.now = now or datetime.now(timezone.utc)
        self.since = self.now - timedelta(hours=max(org.window_hours or 24, 1))
        self.accounts = list(accounts)
        self.by_id = {a.id: a for a in self.accounts}
        self.us_ids = {a.id for a in self.accounts if a.is_us}
        self.posts = [p for p in posts if p.competitor_id in self.by_id]
        self.post_by_id = {p.id: p for p in self.posts}
        self.recent = [p for p in self.posts if utc(p.published_at) >= self.since]
        self.questions = [q for q in questions if q.post_id in self.post_by_id]
        self._baselines()
        self._topics = None

    # ---- baselines and relative performance ----

    def _baselines(self):
        start = self.now - timedelta(days=BASELINE_DAYS)
        per_account = {}
        for p in self.posts:
            age = self.now - utc(p.published_at)
            if p.views is not None and age >= BASELINE_MIN_AGE and utc(p.published_at) >= start:
                per_account.setdefault(p.competitor_id, []).append(p)
        self.baseline = {}
        for aid, ps in per_account.items():
            if len(ps) >= BASELINE_MIN_POSTS:
                self.baseline[aid] = {"median_views": median(p.views for p in ps), "posts": len(ps), "days": BASELINE_DAYS}
        self.relative = {}
        for aid, ps in per_account.items():
            b = self.baseline.get(aid)
            if b and b["median_views"]:
                for p in ps:
                    self.relative[p.id] = round(p.views / b["median_views"], 2)

    # ---- helpers used by recommendations, explorer and opportunities ----

    def is_us(self, post):
        return post.competitor_id in self.us_ids

    def format(self, post):
        """The post's format. Posts saved before formats existed get one from their length
        (live streams can't be told apart until the next Refresh)."""
        f = getattr(post, "format", None)
        if f:
            return f
        if post.platform == "youtube":
            return YouTubeConnector.classify(False, post.duration_seconds)
        return "article" if post.platform == "rss" else None

    def period(self):
        return {"from": iso(self.since), "to": iso(self.now),
                "days": round((self.now - self.since).total_seconds() / 86400, 1)}

    def freshness(self):
        times = [utc(a.last_fetched_at) for a in self.accounts if getattr(a, "last_fetched_at", None)]
        latest = max(times) if times else None
        return {"last_refresh": iso(latest),
                "hours_ago": round((self.now - latest).total_seconds() / 3600, 1) if latest else None}

    def topics(self):
        if self._topics is None:
            rows, our_total = topic_map.coverage_map(
                self.recent, self.accounts, self.cfg["topics"], self.relative, self.questions)
            self._topics = (rows, our_total)
        return self._topics

    def post_card(self, p):
        a = self.by_id[p.competitor_id]
        b = self.baseline.get(p.competitor_id)
        return {
            "type": "post", "id": p.id, "title": p.title, "link": p.link,
            "account": a.name, "account_id": a.id, "is_us": a.is_us, "platform": p.platform,
            "format": self.format(p), "thumbnail": getattr(p, "thumbnail", None),
            "published_at": iso(p.published_at), "views": p.views, "likes": p.likes, "comments": p.comments,
            "duration_seconds": p.duration_seconds, "relative": self.relative.get(p.id),
            "baseline_views": round(b["median_views"]) if b else None, "baseline_posts": b["posts"] if b else 0,
            "metrics_updated_at": iso(getattr(p, "metrics_updated_at", None)),
        }

    def question_card(self, q):
        p = self.post_by_id[q.post_id]
        return {"type": "question", "id": q.id, "text": q.text, "likes": q.likes,
                "published_at": iso(q.published_at), "on_post": p.title, "link": p.link,
                "account": self.by_id[p.competitor_id].name, "is_us": self.is_us(p)}
