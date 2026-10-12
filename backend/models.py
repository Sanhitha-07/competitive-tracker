"""Database tables.

Organization  = a client (news channel, influencer, brand)
Competitor    = one account the client tracks: their own (is_us) or a competitor's,
                on one platform ("rss" = news website feed, "youtube" = YouTube channel)
Post          = one story or video from an account. Always store published_at in UTC.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

PLATFORMS = ("rss", "youtube")


class Organization(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    category: str = "News"
    # How far back to look for coverage gaps and first-to-publish.
    # News moves fast (24 hours); creators post less often (e.g. 30 days = 720).
    window_hours: int = 24


class Competitor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    name: str
    platform: str = "rss"
    source: str  # RSS feed link, or the YouTube handle / channel link the user typed
    is_us: bool = False
    channel_id: Optional[str] = None  # YouTube channel ID, filled in automatically
    subscribers: Optional[int] = None
    last_error: Optional[str] = None


class Post(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("competitor_id", "link"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    competitor_id: int = Field(foreign_key="competitor.id", index=True)
    platform: str = "rss"
    title: str
    link: str
    published_at: datetime  # UTC
    # YouTube only
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    duration_seconds: Optional[int] = None
