"""Database tables.

Organization     = a workspace: a client (creator, streamer, brand, agency, publisher) and
                   its configuration (type, industry, niche, audience, goals, topics, formats)
Competitor       = one account the workspace tracks: their own (is_us) or a competitor's,
                   on one platform (see connectors.CONNECTORS)
Post             = one story or video from an account. Always store published_at in UTC.
MetricSnapshot   = a post's public numbers at one point in time (history)
AccountSnapshot  = an account's public numbers at one point in time (history)
AudienceQuestion = a question found in public comments on a tracked video (no author stored)
Opportunity      = a recommendation the user acted on, and everything that followed:
                   brief -> MediaOps draft -> published post -> measured result
CollectionItem   = a public post saved into a named collection (e.g. "Content Ideas")
ChangeEvent      = a notable change seen in a competitor's public data (one row per event, never repeated)
Experiment       = a content hypothesis the user is testing, and its measured or recorded result
SocialConnection = a workspace's authorized Instagram / Facebook / X connection (encrypted tokens)
OAuthState       = a pending sign-in with a platform, checked when the platform sends the user back
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
    sub_niche: Optional[str] = None
    # User corrections to the topic map: {"aliases": {term: label}, "excluded": [term, ...]}
    topic_rules: Optional[dict] = Field(default=None, sa_column=Column(JSON))


class Competitor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    name: str
    platform: str = "rss"
    source: str  # RSS feed link, or the YouTube handle / channel link the user typed
    is_us: bool = False
    channel_id: Optional[str] = None  # YouTube channel ID, filled in automatically
    thumbnail: Optional[str] = None   # YouTube channel logo URL
    subscribers: Optional[int] = None
    last_error: Optional[str] = None
    last_fetched_at: Optional[datetime] = None
    group: Optional[str] = None  # competitor kind: "direct", "aspirational" or "leader" (see ACCOUNT_GROUPS)
    external_id: Optional[str] = None  # platform id once verified (Instagram user id, Facebook Page id, X user id)
    # False = saved but not checked with the platform yet (e.g. the integration isn't configured).
    # None on older rows = verified the old way (YouTube channel lookup, RSS link check).
    verified: Optional[bool] = None


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
    # YouTube only
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None  # Facebook shares, X reposts; None where the platform has no such count
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


ACCOUNT_GROUPS = {"direct": "Direct competitor", "aspirational": "Aspirational", "leader": "Industry leader"}

OPPORTUNITY_STATUSES = (
    "saved", "brief", "in_mediaops", "scheduled", "published", "evaluated", "completed", "dismissed",
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


class CollectionItem(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("org_id", "collection", "post_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    collection: str
    post_id: int = Field(foreign_key="post.id", index=True)
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class ChangeEvent(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("org_id", "key"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    key: str  # identifies the event, so the same change is never listed twice
    kind: str
    account_id: Optional[int] = Field(default=None, index=True)
    title: str
    detail: dict = Field(default_factory=dict, sa_column=Column(JSON))  # what changed, values, evidence
    status: str = "new"  # new, reviewed, saved
    first_seen_at: datetime = Field(default_factory=_now)


EXPERIMENT_STATUSES = ("planned", "running", "completed", "cancelled")


class Experiment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    hypothesis: str
    reason: Optional[str] = None
    evidence: dict = Field(default_factory=dict, sa_column=Column(JSON))  # frozen copy of what prompted it
    variable_type: str = "other"  # "format", "topic" or "other"
    variable_value: Optional[str] = None
    target_metric: str = "views_vs_usual"  # see experiments.TARGET_METRICS
    success_threshold: float = 1.2
    min_posts: int = 3
    duration_days: int = 28
    status: str = "planned"
    started_at: Optional[datetime] = None
    opportunity_id: Optional[int] = None  # the brief / MediaOps draft made for it
    post_links: list = Field(default_factory=list, sa_column=Column(JSON))
    manual_results: list = Field(default_factory=list, sa_column=Column(JSON))  # [{link, value, note, at}]
    result: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    learning: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# ---- Instagram, Facebook and X connections ----

class SocialConnection(SQLModel, table=True):
    """One workspace's authorized connection to a platform (its own account / Page).
    Tokens are stored encrypted (see secure.py); never sent to the browser."""
    __table_args__ = (UniqueConstraint("org_id", "platform"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    platform: str  # "instagram", "facebook" or "x"
    # connected, needs_page (Meta: choose which Page), expired (reconnect), revoked, error
    status: str = "connected"
    external_id: Optional[str] = None      # the connected user / Page / Instagram account id
    account_name: Optional[str] = None
    username: Optional[str] = None
    access_token_enc: Optional[str] = None
    refresh_token_enc: Optional[str] = None
    expires_at: Optional[datetime] = None
    scopes: Optional[list] = Field(default=None, sa_column=Column(JSON))
    # Meta: Pages the user may pick from: [{id, name, instagram: {id, username} | None}] (no tokens here)
    choices: Optional[list] = Field(default=None, sa_column=Column(JSON))
    page_token_enc: Optional[str] = None   # Meta: the chosen Page's token (encrypted)
    last_error: Optional[str] = None
    connected_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class OAuthState(SQLModel, table=True):
    """A pending authorization: the random `state` sent to the platform and checked on return,
    tied to one workspace and platform, with the PKCE verifier (X). Single use, expires quickly."""
    id: Optional[int] = Field(default=None, primary_key=True)
    state: str = Field(index=True, unique=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    platform: str
    code_verifier: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
