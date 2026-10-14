"""Made-up sample workspaces so the dashboards can be explored before any API key is added.

    python seed_sample.py

Creates three workspaces whose names start with "Sample:" (a bakery on Instagram + Facebook,
a news channel on YouTube + Facebook + website, a fitness creator on YouTube + Instagram),
with posts, follower history and internet trends. Every account, post and trend is invented;
links point to example.com. Only workspaces named "Sample: ..." are replaced: your real data is
never touched. Clicking Refresh on a sample workspace will fail for its accounts (they don't exist).
"""
import random
import sys
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, delete, select

from db import create_tables, engine
from models import (AccountSnapshot, AudienceQuestion, Competitor, MetricSnapshot, Opportunity, Organization, Post,
                    TrendItem)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
NOW = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
rng = random.Random(42)

SAMPLES = [
    {
        "org": dict(name="Sample: Sweet Spot Bakery", creator_type="small_business", category="restaurants",
                    niche="bakery, cakes and Indian sweets", audience="families and office-goers in Hyderabad",
                    goals=["local_customers", "sales"], topics=["diwali sweets", "custom cakes", "eggless"],
                    formats=["reel", "carousel"], platforms=["instagram", "facebook"], region="IN",
                    timezone="Asia/Kolkata", window_hours=720),
        "accounts": [  # name, platform, followers, posts/week, base interactions, is_us, formats
            ("Sweet Spot Bakery", "instagram", 4200, 3, 90, True, ["image", "reel", "carousel"]),
            ("Sweet Spot Bakery", "facebook", 2600, 2, 35, True, ["image", "link"]),
            ("Crumbs & Co", "instagram", 15800, 6, 420, False, ["reel", "reel", "carousel", "image"]),
            ("Crumbs & Co", "facebook", 9100, 4, 120, False, ["video", "image"]),
            ("Mithai Mahal", "instagram", 9800, 5, 260, False, ["reel", "image", "carousel"]),
            ("Oven Story Cafe", "instagram", 6400, 4, 150, False, ["image", "reel"]),
        ],
        "titles": {
            True: ["Fresh bread every morning", "Our new chocolate truffle cake", "Weekend special: rasmalai cake",
                   "Behind the scenes at 5 AM", "Custom cakes for birthdays", "Eggless options now available"],
            False: ["Diwali sweets hampers are here", "Kaju katli in 60 seconds", "Eggless custom cakes for every party",
                    "Diwali sweets gift boxes with free delivery", "How we make our croissants", "Festive menu reveal",
                    "Custom cakes: your photo on a cake", "Customer review: best brownies in town",
                    "Diwali sweets: which one is your favourite?", "Millet cookies for healthy snacking"],
        },
        "trends": [
            ("google_trends", "diwali sweets", "100000+", None, None),
            ("google_news", "diwali sweets", None, 64, 2.4),
            ("google_news", "custom cakes", None, 18, 1.1),
            ("google_trends", "millet cookies", "20000+", None, None),
            ("google_trends", "food poisoning cases at sweet shop", "50000+", None, None),
        ],
    },
    {
        "org": dict(name="Sample: Metro News 24", creator_type="news_channel", category="news",
                    niche="Hyderabad and Telangana news", audience="Telugu and English viewers in Hyderabad",
                    goals=["timeliness", "more_views"], topics=["metro", "rain alert", "traffic"],
                    formats=["short", "video", "live"], platforms=["youtube", "facebook"], region="IN",
                    timezone="Asia/Kolkata", window_hours=24),
        "accounts": [
            ("Metro News 24", "youtube", 820000, 28, 30000, True, ["short", "video", "video", "live"]),
            ("Metro News 24", "facebook", 410000, 20, 900, True, ["video", "link"]),
            ("Deccan Live TV", "youtube", 2400000, 42, 85000, False, ["short", "short", "video", "live"]),
            ("Deccan Live TV", "facebook", 1300000, 30, 2600, False, ["video", "link", "image"]),
            ("City Pulse News", "youtube", 560000, 35, 22000, False, ["short", "video"]),
            ("Hyderabad Today", "facebook", 690000, 25, 1400, False, ["link", "image", "video"]),
        ],
        "titles": {
            True: ["Metro phase 2 work begins on airport line", "Heavy rain alert for Hyderabad tonight",
                   "Traffic diversions for Ganesh immersion", "Gold price today in Hyderabad", "Morning headlines"],
            False: ["Heavy rain alert: IMD issues orange alert for Hyderabad", "Metro fares to go up from November",
                    "Traffic jam on ORR after lorry breakdown", "Rain alert: schools closed tomorrow",
                    "Metro phase 2: land acquisition update", "Flood in low-lying areas after overnight rain",
                    "Traffic police new challan rules explained", "Hyderabad biryani festival this weekend",
                    "Cricket: Hyderabad team squad announced", "Rain alert for 5 districts"],
        },
        "trends": [
            ("google_trends", "hyderabad rain", "200000+", None, None),
            ("google_news", "rain alert", None, 97, 3.1),
            ("google_news", "metro", None, 55, 1.2),
            ("google_trends", "flood in low lying areas kills 2", "50000+", None, None),
            ("google_trends", "assembly election dates", "100000+", None, None),
            ("youtube_trending", "Biryani festival 2026 full tour", None, 410000, None),
        ],
    },
    {
        "org": dict(name="Sample: FitWithAsha", creator_type="influencer", category="fitness",
                    niche="home workouts and Indian diet for women", audience="working women 25-40",
                    goals=["grow_audience", "engagement"], topics=["protein", "home workout", "pcos"],
                    formats=["short", "reel"], platforms=["youtube", "instagram"], region="IN",
                    timezone="Asia/Kolkata", window_hours=720),
        "accounts": [
            ("FitWithAsha", "youtube", 185000, 3, 21000, True, ["short", "short", "video"]),
            ("FitWithAsha", "instagram", 240000, 5, 5200, True, ["reel", "carousel"]),
            ("Desi Fit Life", "youtube", 690000, 5, 64000, False, ["short", "video", "long"]),
            ("Desi Fit Life", "instagram", 510000, 7, 9800, False, ["reel", "reel", "carousel"]),
            ("Strong Didi", "youtube", 320000, 4, 30000, False, ["short", "short", "video"]),
            ("Yoga With Meera", "instagram", 410000, 6, 7600, False, ["reel", "image", "carousel"]),
        ],
        "titles": {
            True: ["15 minute home workout for beginners", "High protein Indian breakfast", "Fat loss myths busted",
                   "My weekly meal prep", "Home workout with no equipment"],
            False: ["PCOS diet plan that actually works", "Protein for vegetarians: 5 easy foods",
                    "30 day home workout challenge", "PCOS workout routine at home", "Walking vs running for fat loss",
                    "High protein dal recipes", "Home workout for belly fat", "Yoga for back pain",
                    "What I eat in a day: protein edition", "Creatine for women: myths and facts"],
        },
        "trends": [
            ("google_news", "pcos", None, 41, 1.9),
            ("google_news", "protein", None, 88, 1.0),
            ("google_trends", "creatine for women", "20000+", None, None),
            ("youtube_trending", "30 Day Home Workout Challenge | Day 1", None, 950000, None),
            ("google_trends", "gym trainer arrested", "10000+", None, None),
        ],
    },
]


def _clear(s, org):
    ids = [a.id for a in s.exec(select(Competitor).where(Competitor.org_id == org.id)).all()]
    if ids:
        post_ids = [p.id for p in s.exec(select(Post).where(Post.competitor_id.in_(ids))).all()]
        if post_ids:
            s.exec(delete(MetricSnapshot).where(MetricSnapshot.post_id.in_(post_ids)))
            s.exec(delete(AudienceQuestion).where(AudienceQuestion.post_id.in_(post_ids)))
        s.exec(delete(AccountSnapshot).where(AccountSnapshot.competitor_id.in_(ids)))
        s.exec(delete(Post).where(Post.competitor_id.in_(ids)))
        s.exec(delete(Competitor).where(Competitor.org_id == org.id))
    s.exec(delete(TrendItem).where(TrendItem.org_id == org.id))
    s.exec(delete(Opportunity).where(Opportunity.org_id == org.id))
    s.delete(org)


def _post(account, i, when, title, fmt, base):
    lift = rng.lognormvariate(0, 0.45) * (3.5 if rng.random() < 0.05 else 1)  # a few posts take off
    if account.platform == "youtube":
        views = int(base * lift * (1.6 if fmt == "short" else 1))
        likes, comments, shares = int(views * rng.uniform(.02, .05)), int(views * rng.uniform(.001, .004)), None
        dur = {"short": rng.randint(20, 59), "video": rng.randint(180, 900), "long": rng.randint(1300, 2400),
               "live": rng.randint(1800, 5400)}[fmt]
    else:
        inter = base * lift * (1.5 if fmt in ("reel", "video") else 1)
        likes, comments = int(inter * .9), int(inter * .07)
        shares = int(inter * .05) if account.platform == "facebook" else None
        views = int(inter * rng.uniform(15, 30)) if fmt == "reel" else None
        dur = None
    slug = account.name.lower().replace(" ", "").replace("&", "")
    return Post(competitor_id=account.id, platform=account.platform, title=title,
                link=f"https://example.com/{account.platform}/{slug}/{i}", published_at=when, format=fmt,
                tags=[w for w in title.lower().replace(":", "").split() if len(w) > 4][:4], views=views, likes=likes,
                comments=comments, shares=shares, duration_seconds=dur, metrics_updated_at=NOW)


def seed():
    create_tables()
    with Session(engine) as s:
        for old in s.exec(select(Organization).where(Organization.name.startswith("Sample: "))).all():
            _clear(s, old)
        s.commit()
        for spec in SAMPLES:
            org = Organization(**spec["org"])
            s.add(org)
            s.commit()
            s.refresh(org)
            n_posts = 0
            for name, platform, followers, per_week, base, is_us, fmts in spec["accounts"]:
                acc = Competitor(org_id=org.id, name=name, platform=platform, source=f"sample:{name}", is_us=is_us,
                                 subscribers=followers, last_fetched_at=NOW - timedelta(hours=2))
                s.add(acc)
                s.commit()
                s.refresh(acc)
                titles = spec["titles"][is_us]
                total = int(per_week * 60 / 7)
                for i in range(total):
                    when = NOW - timedelta(hours=rng.uniform(1, 60 * 24))
                    when = when.replace(hour=rng.choice([7, 9, 12, 13, 18, 19, 20, 21]) if platform != "youtube" or per_week < 10 else when.hour)
                    if when > NOW:
                        when -= timedelta(days=1)
                    p = _post(acc, i, when, titles[i % len(titles)] + ("" if i < len(titles) else f" (part {i // len(titles) + 1})"),
                              rng.choice(fmts), base)
                    s.add(p)
                    n_posts += 1
                for d in range(30, -1, -3):  # follower history: competitors grow a bit faster
                    growth = (0.0009 if is_us else 0.0016) * (30 - d)
                    s.add(AccountSnapshot(competitor_id=acc.id, captured_at=NOW - timedelta(days=d),
                                          subscribers=int(followers * (1 - 0.05) * (1 + growth) / (1 + 0.0016 * 30) * 1.05)))
            for source, title, traffic, volume, momentum in spec["trends"]:
                related = [{"title": f"{title.title()}: what we know", "link": "https://example.com/news/1",
                            "source": "Example News", "published_at": None}]
                s.add(TrendItem(org_id=org.id, key=f"{source}:{title}", source=source, title=title, query=title if source == "google_news" else None,
                                link="https://example.com/trend", traffic=traffic, volume=volume, momentum=momentum,
                                published_at=NOW - timedelta(hours=rng.randint(1, 20)), fetched_at=NOW - timedelta(minutes=30),
                                related=related))
            s.commit()
            print(f"{org.name}: {len(spec['accounts'])} accounts, {n_posts} posts, {len(spec['trends'])} trends")
    print("\nSample data ready. Start the app and pick a 'Sample:' workspace.")


if __name__ == "__main__":
    seed()
