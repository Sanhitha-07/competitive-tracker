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
    "small_business": "Small or local business (shop, restaurant, salon, clinic…)",
    "business": "Business",
    "brand": "Brand",
    "ecommerce": "Online store / D2C brand",
    "agency": "Agency",
    "publisher": "News / media publisher (digital)",
    "news_channel": "News channel (TV / video news)",
    "nonprofit": "Non-profit / NGO",
    "public_figure": "Public figure",
}

# How careful suggestions must be around sensitive news (tragedies, disasters, politics...).
#   strict    brands and businesses: never tie content or promotions to sensitive events
#   standard  creators: only with real expertise, never monetised or sensationalised
#   newsroom  news organisations: cover it, with verification and care
BRAND_SAFETY = {
    "strict": "Strict: avoid sensitive news entirely (brands, businesses)",
    "standard": "Standard: only with care and expertise (creators)",
    "newsroom": "Newsroom: cover sensitive news responsibly (news organisations)",
}

# Starting values per creator type. All of them can be changed in Workspace settings.
PROFILES = {
    "influencer": {"safety": "standard", "goals": ["grow_audience", "engagement"]},
    "creator": {"safety": "standard", "goals": ["grow_audience", "authority"]},
    "youtuber": {"safety": "standard", "goals": ["more_views", "grow_audience"]},
    "streamer": {"safety": "standard", "goals": ["community", "consistency"]},
    "small_business": {"safety": "strict", "goals": ["local_customers", "sales"]},
    "business": {"safety": "strict", "goals": ["brand_awareness", "sales"]},
    "brand": {"safety": "strict", "goals": ["brand_awareness", "engagement"]},
    "ecommerce": {"safety": "strict", "goals": ["sales", "engagement"]},
    "agency": {"safety": "strict", "goals": ["engagement", "grow_audience"]},
    "publisher": {"safety": "newsroom", "goals": ["timeliness", "grow_audience"], "time_sensitive": True},
    "news_channel": {"safety": "newsroom", "goals": ["timeliness", "more_views"], "time_sensitive": True},
    "nonprofit": {"safety": "standard", "goals": ["brand_awareness", "community"]},
    "public_figure": {"safety": "standard", "goals": ["engagement", "authority"]},
}
NEWS_TYPES = {"publisher", "news_channel"}
BUSINESS_TYPES = {"small_business", "business", "brand", "ecommerce", "agency"}

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
    "restaurants": ("Restaurants, cafes and food business", 24 * 30, False),
    "retail": ("Retail and local shops", 24 * 30, False),
    "health": ("Healthcare, clinics and pharmacy", 24 * 30, False),
    "real_estate": ("Real estate and property", 24 * 30, False),
    "automotive": ("Automotive", 24 * 30, False),
    "sports": ("Sports", 24 * 7, True),
    "music": ("Music and arts", 24 * 30, False),
    "services": ("Professional and local services", 24 * 30, False),
    "politics": ("Politics and public affairs", 24 * 2, True),
    "other": ("Other", 24 * 30, False),
}

# Words that describe each industry, used only to decide whether something trending on the
# internet is related to a workspace (never to make a recommendation on their own).
INDUSTRY_KEYWORDS = {
    "fitness": "fitness workout gym exercise yoga protein diet weight loss running marathon wellness nutrition",
    "beauty": "beauty makeup skincare skin hair fashion style outfit cosmetics fragrance nails",
    "gaming": "game gaming gamer esports playstation xbox nintendo steam console valorant minecraft bgmi",
    "education": "exam education course learning study students school university coding python programming tutorial",
    "technology": "tech smartphone iphone android launch ai laptop gadget app software chip apple samsung google",
    "travel": "travel trip tourism flight hotel visa destination holiday beach trek",
    "food": "food recipe cooking restaurant chef dish cuisine baking street food sweets",
    "finance": "stock market sensex nifty shares economy budget tax gst rbi interest rate inflation ipo crypto bank",
    "news": "",
    "ecommerce": "sale discount shopping offer deal online shopping delivery festive",
    "entertainment": "movie film trailer box office series netflix actor actress song celebrity ott release",
    "restaurants": "food restaurant cafe dining recipe chef menu biryani coffee sweets",
    "retail": "sale shopping offer discount store festive deal fashion grocery",
    "health": "health hospital doctor clinic disease treatment medicine vaccine wellness diet fever",
    "real_estate": "property real estate housing home loan apartment rent land construction",
    "automotive": "car bike ev electric vehicle launch suv scooter motor",
    "sports": "cricket football match ipl league tournament world cup score team player olympics kabaddi",
    "music": "music song album concert singer band tour",
    "services": "service business tax gst law startup small business",
    "politics": "election government minister parliament policy vote party",
    "other": "",
}

# YouTube "Trending" category per industry (YouTube's own video categories). Missing = all videos.
YOUTUBE_CATEGORY = {
    "gaming": "20", "education": "27", "technology": "28", "beauty": "26", "food": "26", "fitness": "26",
    "travel": "19", "news": "25", "politics": "25", "entertainment": "24", "sports": "17", "music": "10",
    "automotive": "2", "restaurants": "26", "retail": "26", "ecommerce": "26",
}

REGIONS = {
    "IN": "India", "US": "United States", "GB": "United Kingdom", "AE": "United Arab Emirates",
    "SG": "Singapore", "AU": "Australia", "CA": "Canada", "DE": "Germany", "FR": "France",
    "BR": "Brazil", "ID": "Indonesia", "JP": "Japan", "NG": "Nigeria", "ZA": "South Africa",
    "SA": "Saudi Arabia", "PK": "Pakistan", "BD": "Bangladesh", "LK": "Sri Lanka", "NP": "Nepal",
}
DEFAULT_REGION = "IN"

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
    "timeliness": ("Be first on time-sensitive topics", {"topic_gap": 1.3, "publishing_pattern": 1.2, "trend": 1.5}),
    "brand_awareness": ("Build brand awareness", {"trend": 1.3, "outlier": 1.2, "format_test": 1.1}),
    "local_customers": ("Reach local customers", {"audience_question": 1.3, "trend": 1.2, "publishing_pattern": 1.1}),
    "ride_trends": ("Join relevant trends early", {"trend": 1.6}),
}

# Formats the user can prefer. "detectable" = the tracker can tell this format apart in the data.
FORMATS = {
    "short": ("Short video (≤ 60s)", True),
    "video": ("Standard video", True),
    "long": ("Long-form video (20 min+)", True),
    "live": ("Live stream", True),
    "article": ("Article / blog post", True),
    "image": ("Image post", True),
    "carousel": ("Carousel (several photos or videos)", True),
    "reel": ("Reel (Instagram)", True),
    "post": ("Text or link post (Facebook, X)", True),
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


def profile(creator_type):
    return PROFILES.get(creator_type or "", {"safety": "standard", "goals": []})


def safety(org):
    if getattr(org, "brand_safety", None) in BRAND_SAFETY:
        return org.brand_safety
    return profile(org.creator_type)["safety"]


def region(org):
    r = (getattr(org, "region", None) or "").upper()
    return r if r in REGIONS else DEFAULT_REGION


def config(org):
    """The organization's configuration with defaults filled in, as plain data."""
    ind = industry_id(org)
    label, _, sensitive = INDUSTRIES[ind]
    if profile(org.creator_type).get("time_sensitive"):
        sensitive = True
    return {
        "creator_type": org.creator_type,
        "industry": ind,
        "industry_label": label if ind != "other" or not org.niche else org.niche,
        "niche": org.niche or "",
        "sub_niche": getattr(org, "sub_niche", None) or "",
        "audience": org.audience or "",
        "goals": [g for g in (org.goals or []) if g in GOALS],
        "topics": [t for t in (org.topics or []) if t and t.strip()],
        "formats": [f for f in (org.formats or []) if f in FORMATS],
        "platforms": org.platforms or [],
        "timezone": org.timezone or DEFAULT_TIMEZONE,
        "time_sensitive": sensitive if org.time_sensitive is None else org.time_sensitive,
        "window_hours": org.window_hours,
        "topic_rules": {"aliases": (getattr(org, "topic_rules", None) or {}).get("aliases") or {},
                        "excluded": (getattr(org, "topic_rules", None) or {}).get("excluded") or []},
        "region": region(org),
        "region_label": REGIONS[region(org)],
        "brand_safety": safety(org),
        "brand_safety_label": BRAND_SAFETY[safety(org)],
        "is_news": org.creator_type in NEWS_TYPES or ind in ("news", "politics"),
        "is_business": org.creator_type in BUSINESS_TYPES,
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
        "creator_types": [{"id": k, "label": v, "brand_safety": profile(k)["safety"], "goals": profile(k)["goals"],
                           "time_sensitive": bool(profile(k).get("time_sensitive"))} for k, v in CREATOR_TYPES.items()],
        "brand_safety": [{"id": k, "label": v} for k, v in BRAND_SAFETY.items()],
        "regions": [{"id": k, "label": v} for k, v in REGIONS.items()],
        "industries": [
            {"id": k, "label": v[0], "window_hours": v[1], "time_sensitive": v[2]} for k, v in INDUSTRIES.items()
        ],
        "goals": [{"id": k, "label": v[0]} for k, v in GOALS.items()],
        "formats": [{"id": k, "label": v[0], "detectable": v[1]} for k, v in FORMATS.items()],
    }
