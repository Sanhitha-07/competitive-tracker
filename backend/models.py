"""Database tables.

Organization     = a workspace: a client (creator, streamer, brand, agency, publisher) and
                   its configuration (type, industry, niche, audience, goals, topics, formats)
Competitor       = one account the workspace tracks: their own (is_us) or a competitor's,
                   on one platform (see connectors.CONNECTORS)
Post             = one story or video from an account. Always store published_at in UTC.
MetricSnapshot   = a post's public numbers at one point in time (history)
AccountSnapshot  = an account's public numbers at one point in time (history)
AudienceQuestion = a question found in public comments on a tracked video (no author stored)
TrendItem        = something trending on the internet (Google Trends, news, YouTube trending)
                   that matched a workspace, with its sensitivity rating
Opportunity      = a recommendation the user acted on, and everything that followed:
                   brief -> MediaOps draft -> published post -> measured result
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def _now():
    return datetime.now(timezone.utc)


class Organization(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    category: str = "News"  # industry
    # How far back to look for coverage gaps and first-to-publish.
    # News moves fast (24 hours); creators post less often (e.g. 30 days = 720).
    window_hours: int = 24
    # Workspace configuration. Lists are stored as JSON; older rows may have NULL.
    creator_type: Optional[str] = None
    niche: Optional[str] = None
    audience: Optional[str] = None
    goals: Optional[list] = Field(default=None, sa_column=Column(JSON))
    topics: Optional[list] = Field(default=None, sa_column=Column(JSON))
    formats: Optional[list] = Field(default=None, sa_column=Column(JSON))
    platforms: Optional[list] = Field(default=None, sa_column=Column(JSON))
    timezone: Optional[str] = None  # e.g. "Asia/Kolkata"; used for posting-time patterns
    time_sensitive: Optional[bool] = None  # show First to Publish (news, launches, live events)
    region: Optional[str] = None  # 2-letter country code for trends, e.g. "IN"
    brand_safety: Optional[str] = None  # "strict" | "standard" | "newsroom"; default from creator type


class Competitor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    name: str
    platform: str = "rss"
    source: str  # RSS feed link, or the YouTube handle / channel link the user typed
    is_us: bool = False
    channel_id: Optional[str] = None  # platform account ID (YouTube channel, Instagram user, Facebook Page)
    thumbnail: Optional[str] = None   # account logo URL
    subscribers: Optional[int] = None  # audience size: subscribers (YouTube) or followers (Instagram, Facebook)
    last_error: Optional[str] = None
    last_fetched_at: Optional[datetime] = None


class Post(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("competitor_id", "link"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    competitor_id: int = Field(foreign_key="competitor.id", index=True)
    platform: str = "rss"
    title: str
    link: str
    published_at: datetime  # UTC
    thumbnail: Optional[str] = None
    format: Optional[str] = None  # connector-defined: "short", "video", "long", "live", "article"
    tags: Optional[list] = Field(default=None, sa_column=Column(JSON))  # creator tags / RSS categories
    # Public numbers; None when the platform doesn't expose them (RSS has none,
    # Instagram views are Reels-only, Facebook "likes" = all reactions)
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    duration_seconds: Optional[int] = None
    metrics_updated_at: Optional[datetime] = None
    questions_checked_at: Optional[datetime] = None


class MetricSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="post.id", index=True)
    captured_at: datetime = Field(default_factory=_now, index=True)
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None


class AccountSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    competitor_id: int = Field(foreign_key="competitor.id", index=True)
    captured_at: datetime = Field(default_factory=_now, index=True)
    subscribers: Optional[int] = None
    posts_tracked: Optional[int] = None


class AudienceQuestion(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("post_id", "comment_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="post.id", index=True)
    comment_id: str
    text: str
    likes: int = 0
    published_at: datetime


OPPORTUNITY_STATUSES = (
    "saved", "brief", "in_mediaops", "scheduled", "published", "evaluated", "dismissed",
)


class Opportunity(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    key: str = Field(index=True)  # stable id of the observation, e.g. "topic_gap:protein"
    kind: str
    title: str
    status: str = "saved"
    # A frozen copy of the opportunity as it was shown, so evidence survives later refreshes.
    snapshot: dict = Field(default_factory=dict, sa_column=Column(JSON))
    brief: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    planned_for: Optional[datetime] = None
    mediaops_ref: Optional[str] = None      # Draft Package id/link returned by or entered from MediaOps
    published_link: Optional[str] = None    # link of our published post
    published_post_id: Optional[int] = None  # matched Post row once our account is refreshed
    outcome: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    history: list = Field(default_factory=list, sa_column=Column(JSON))  # [{status, at, note}]
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class TrendItem(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("org_id", "key"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    key: str  # source + normalized title, so the same trend isn't saved twice
    source: str  # "google_trends" | "google_news" | "youtube_trending"
    title: str
    link: Optional[str] = None
    summary: Optional[str] = None
    traffic: Optional[str] = None       # e.g. "10000+" searches (Google Trends only)
    volume: Optional[int] = None        # articles/videos found for a topic search
    momentum: Optional[float] = None    # recent volume ÷ earlier volume (topic searches)
    query: Optional[str] = None         # the workspace topic that was searched, if any
    picture: Optional[str] = None
    published_at: Optional[datetime] = None
    fetched_at: datetime = Field(default_factory=_now, index=True)
    related: list = Field(default_factory=list, sa_column=Column(JSON))  # [{title, link, source, published_at}]
