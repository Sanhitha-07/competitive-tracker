"""Workspace configuration: who the user is and what they care about.

Nothing here is a recommendation. These are the option lists shown in the settings form,
and starting defaults per industry (comparison window, likely formats) that the user can change.
Recommendations come only from collected data, ranked by this configuration.
"""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CREATOR_TYPES = {
    "influencer": "Influencer",
    "creator": "Individual content creator",
    "youtuber": "YouTuber",
    "streamer": "Streamer",
    "business": "Business",
    "brand": "Brand",
    "agency": "Agency",
    "publisher": "News / media publisher",
}

# id: (label, default window in hours, time-sensitive by default)
INDUSTRIES = {
    "fitness": ("Fitness and wellness", 24 * 30, False),
    "beauty": ("Beauty and fashion", 24 * 30, False),
    "gaming": ("Gaming and streaming", 24 * 14, False),
    "education": ("Education and programming", 24 * 30, False),
    "technology": ("Technology", 24 * 14, False),
    "travel": ("Travel and lifestyle", 24 * 30, False),
    "food": ("Food and cooking", 24 * 30, False),
    "finance": ("Finance and business", 24 * 14, False),
    "news": ("News and media", 24, True),
    "ecommerce": ("E-commerce and product brands", 24 * 30, False),
    "entertainment": ("Entertainment", 24 * 14, False),
    "other": ("Other", 24 * 30, False),
}

# Old free-text categories from before the workspace settings existed.
LEGACY_CATEGORIES = {
    "News": "news", "Fitness": "fitness", "Technology": "technology", "Food": "food",
    "Travel": "travel", "Gaming": "gaming", "Fashion & Beauty": "beauty",
    "Education": "education", "Business": "finance", "Other": "other",
}

# Goals change how opportunity kinds are ranked (weights), never what the data says.
GOALS = {
    "grow_audience": ("Grow my audience", {"outlier": 1.3, "topic_gap": 1.2, "format_test": 1.1}),
    "more_views": ("Get more views per post", {"outlier": 1.4, "format_test": 1.2}),
    "engagement": ("Increase engagement", {"audience_question": 1.4, "format_test": 1.1}),
    "community": ("Answer my audience's questions", {"audience_question": 1.5}),
    "authority": ("Build authority in my niche", {"topic_gap": 1.3, "audience_question": 1.2}),
    "sales": ("Drive sales or leads", {"audience_question": 1.3, "topic_gap": 1.1}),
    "consistency": ("Publish more consistently", {"publishing_pattern": 1.5}),
    "timeliness": ("Be first on time-sensitive topics", {"topic_gap": 1.3, "publishing_pattern": 1.2}),
}

# Formats the user can prefer. "detectable" = the tracker can tell this format apart in the data.
FORMATS = {
    "short": ("Short video (≤ 60s)", True),
    "video": ("Standard video", True),
    "long": ("Long-form video (20 min+)", True),
    "live": ("Live stream", True),
    "article": ("Article / blog post", True),
    "image": ("Image or carousel post", False),
    "podcast": ("Podcast / audio", False),
    "newsletter": ("Newsletter", False),
}

DEFAULT_TIMEZONE = "Asia/Kolkata"


def industry_id(org):
    cat = (org.category or "").strip()
    if cat in INDUSTRIES:
        return cat
    return LEGACY_CATEGORIES.get(cat, "other")


def tz(org):
    try:
        return ZoneInfo(org.timezone or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def config(org):
    """The organization's configuration with defaults filled in, as plain data."""
    ind = industry_id(org)
    label, _, sensitive = INDUSTRIES[ind]
    return {
        "creator_type": org.creator_type,
        "industry": ind,
        "industry_label": label if ind != "other" or not org.niche else org.niche,
        "niche": org.niche or "",
        "audience": org.audience or "",
        "goals": [g for g in (org.goals or []) if g in GOALS],
        "topics": [t for t in (org.topics or []) if t and t.strip()],
        "formats": [f for f in (org.formats or []) if f in FORMATS],
        "platforms": org.platforms or [],
        "timezone": org.timezone or DEFAULT_TIMEZONE,
        "time_sensitive": sensitive if org.time_sensitive is None else org.time_sensitive,
        "window_hours": org.window_hours,
        "configured": bool(org.creator_type and (org.niche or org.topics or org.goals)),
    }


def goal_weight(cfg, kind):
    """Multiply weights of every selected goal that mentions this kind (1.0 if none)."""
    w = 1.0
    for g in cfg["goals"]:
        w *= GOALS[g][1].get(kind, 1.0)
    return w


def options():
    """Everything the settings form needs."""
    return {
        "creator_types": [{"id": k, "label": v} for k, v in CREATOR_TYPES.items()],
        "industries": [
            {"id": k, "label": v[0], "window_hours": v[1], "time_sensitive": v[2]} for k, v in INDUSTRIES.items()
        ],
        "goals": [{"id": k, "label": v[0]} for k, v in GOALS.items()],
        "formats": [{"id": k, "label": v[0], "detectable": v[1]} for k, v in FORMATS.items()],
    }
