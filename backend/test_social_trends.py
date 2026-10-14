"""Instagram, Facebook, internet trends, sensitivity and the Dashboard. Run with:  python -m pytest -q
No internet needed: Meta's API is replaced by canned responses and trends are inserted directly."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as Row

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

import config
import connectors
import main
import recommend
import sensitivity
import trends
from dataset import Dataset
from db import engine
from models import Competitor, Post, TrendItem
from performance import compare

NOW = datetime.now(timezone.utc)


# ---- Instagram data through the API (posts inserted directly: no Meta calls) ----

def test_interactions_add_up_only_public_counts():
    assert connectors.interactions(Row(likes=120, comments=9, shares=4)) == 133
    assert connectors.interactions(Row(likes=None, comments=5, shares=None)) == 5  # hidden likes aren't 0
    assert connectors.interactions(Row(likes=None, comments=None, shares=None)) is None
    assert connectors.performance_metric("instagram") == "interactions" and connectors.performance_metric("youtube") == "views"


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="module")
def bakery(client):
    """Our bakery + 2 competitors on Instagram, 12 posts each; one of rival1's posts is far above its usual."""
    r = client.post("/organizations", json={"name": "Sweet Spot Bakery", "creator_type": "small_business",
                                            "category": "restaurants", "niche": "bakery and sweets", "region": "IN"})
    assert r.status_code == 201, r.text
    org = r.json()
    accounts = {"ourbakery": (2000, 40, True), "rival1": (8000, 160, False), "rival2": (5000, 120, False)}
    with Session(engine) as s:
        for name, (followers, likes, us) in accounts.items():
            a = Competitor(org_id=org["id"], name=name, platform="instagram", source=f"@{name}", is_us=us,
                           channel_id=f"ig-{name}", subscribers=followers, last_fetched_at=NOW)
            s.add(a)
            s.commit()
            s.refresh(a)
            for i in range(12):
                reel = i % 3 == 0
                s.add(Post(competitor_id=a.id, platform="instagram",
                           title=f"{'Diwali sweets' if i % 2 else 'Fresh bread'} special",
                           link=f"https://www.instagram.com/p/{name}{i}/", published_at=NOW - timedelta(days=3 + i * 2),
                           format="reel" if reel else "image", tags=[name],
                           views=5000 if reel else None, likes=likes * (8 if (name == "rival1" and i == 1) else 1),
                           comments=5, shares=None))
        s.commit()
    return org


def test_business_profile_defaults(client, bakery):
    cfg = client.get(f"/organizations/{bakery['id']}/config").json()
    assert cfg["brand_safety"] == "strict" and cfg["is_business"]
    assert cfg["goals"] == ["local_customers", "sales"]  # starting goals for a small business


def test_instagram_performance_uses_interactions(client, bakery):
    perf = client.get(f"/organizations/{bakery['id']}/performance").json()
    ig = perf["platforms"]["instagram"]
    assert ig["metric"] == "interactions" and ig["us"]["posts"] == 12
    # 45 interactions on 2000 followers = 2.25% per post
    assert ig["us"]["engagement_rate"] == pytest.approx(2.25, abs=0.01)
    assert ig["us"]["video_pct"] == 33 and ig["us"]["median_reel_views"] == 5000
    assert ig["top_posts"][0]["account"] == "rival1"


def test_instagram_outlier_is_relative_to_own_account(client, bakery):
    recs = client.get(f"/organizations/{bakery['id']}/recommendations").json()["recommendations"]
    outliers = [r for r in recs if r["kind"] == "outlier"]
    assert outliers and "interactions" in outliers[0]["observed"] and "rival1" in outliers[0]["title"]


def test_overview_explains_in_plain_language(client, bakery):
    d = client.get(f"/organizations/{bakery['id']}/briefing").json()
    assert d["period"]["days"] == 30 and d["briefing"]["headline"]
    assert all({"tone", "title", "text", "tab"} <= set(x) for x in d["briefing"]["items"])
    assert {k["id"] for k in d["kpis"]} >= {"posts", "sov", "relative", "trends"}
    sov = {r["name"]: r for r in d["share_of_voice"]["rows"]}
    assert sum(r["share_posts"] for r in sov.values()) in (99, 100, 101)
    assert len(d["activity"]["series"]) == 3 and len(d["activity"]["buckets"]) == 8
    assert d["engagement"][0]["platform"] == "instagram"
    assert d["ai_available"] is False


def test_ai_briefing_off_without_key(client, bakery):
    r = client.post(f"/organizations/{bakery['id']}/briefing/ai")
    assert r.status_code == 400 and "ANTHROPIC_API_KEY" in r.json()["detail"]


# ---- trends ----

TRENDS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>diwali sweets</title><ht:approx_traffic>50000+</ht:approx_traffic>
<pubDate>Tue, 13 Oct 2026 09:20:00 -0700</pubDate>
<ht:news_item><ht:news_item_title>Diwali sweets demand soars</ht:news_item_title><ht:news_item_url>https://e.com/a</ht:news_item_url><ht:news_item_source>ET</ht:news_item_source></ht:news_item>
<ht:news_item><ht:news_item_title>Best sweet shops</ht:news_item_title><ht:news_item_url>https://e.com/b</ht:news_item_url><ht:news_item_source>HT</ht:news_item_source></ht:news_item>
</item>
<item><title>football final</title><ht:approx_traffic>10000+</ht:approx_traffic><pubDate>Tue, 13 Oct 2026 08:00:00 -0700</pubDate></item>
</channel></rss>"""

NEWS_XML = b"""<?xml version="1.0"?><rss><channel>
<item><title>Bakery chain expands - Mint</title><link>https://n.com/1</link><source url="https://mint">Mint</source><pubDate>Tue, 13 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>Sweets prices up</title><link>https://n.com/2</link><pubDate>Mon, 12 Oct 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_parse_google_trends_keeps_every_news_item():
    items = trends.parse_google_trends(TRENDS_XML)
    assert [i["title"] for i in items] == ["diwali sweets", "football final"]
    assert items[0]["traffic"] == "50000+" and len(items[0]["news"]) == 2 and items[0]["news"][1]["source"] == "HT"


def test_parse_google_news_strips_source_suffix():
    items = trends.parse_google_news(NEWS_XML)
    assert items[0]["title"] == "Bakery chain expands" and items[0]["source"] == "Mint"


def test_momentum_needs_enough_articles():
    now = datetime(2026, 10, 13, tzinfo=timezone.utc)
    recent = [{"published_at": now - timedelta(hours=h)} for h in (1, 5, 10, 20, 30, 40)]
    earlier = [{"published_at": now - timedelta(days=d)} for d in (3, 5)]
    assert trends.momentum(recent + earlier, now) == pytest.approx(7.5)
    assert trends.momentum(recent[:2], now) is None


def test_refresh_saves_only_relevant_trends(monkeypatch, bakery):
    monkeypatch.setattr(config, "TRENDS_GOOGLE_TRENDS", True)
    monkeypatch.setattr(config, "TRENDS_GOOGLE_NEWS", True)
    monkeypatch.setattr(trends, "_http", lambda url, timeout=20: TRENDS_XML if "trends.google" in url else NEWS_XML)
    with Session(engine) as s:
        org = s.get(main.Organization, bakery["id"])
        out = trends.refresh(s, org, ["diwali sweets"], force=True)
        assert {x["source"] for x in out["sources"]} == {"google_trends", "google_news"}
        saved = {t.title for t in s.exec(main.select(TrendItem).where(TrendItem.org_id == org.id)).all()}
    assert "diwali sweets" in saved and "football final" not in saved  # sport isn't relevant to a bakery


def test_trends_endpoint_rates_sensitivity_and_coverage(client, bakery):
    with Session(engine) as s:
        s.add(TrendItem(org_id=bakery["id"], key="google_trends:bakery fire", source="google_trends",
                        title="bakery fire accident kills 3", traffic="20000+", published_at=NOW, fetched_at=NOW, related=[]))
        s.commit()
    data = client.get(f"/organizations/{bakery['id']}/trends").json()
    by_title = {t["title"]: t for t in data["trends"]}
    sweets = by_title["diwali sweets"]
    assert sweets["sensitivity"]["level"] == "safe" and sweets["advice"]["action"] == "go"
    assert set(sweets["coverage"]["competitors"]) == {"rival1", "rival2"} and sweets["coverage"]["yours"] >= 1
    fire = by_title["bakery fire accident kills 3"]
    assert fire["sensitivity"]["level"] == "sensitive" and fire["advice"]["action"] == "avoid" and fire["angles"] == []
    recs = client.get(f"/organizations/{bakery['id']}/recommendations").json()["recommendations"]
    trend_titles = [r["topic"] for r in recs if r["kind"] == "trend"]
    assert "diwali sweets" in trend_titles and not any("fire" in t for t in trend_titles)  # never suggested to a brand


# ---- sensitivity ----

@pytest.mark.parametrize("text,level", [
    ("Full body workout for beginners", "safe"), ("Diwali sale: 50% off sweets", "safe"), ("Star Wars trailer", "safe"),
    ("India win away match", "safe"), ("Earthquake in Nepal kills 30", "sensitive"), ("Actor passes away at 67", "sensitive"),
    ("Lok Sabha election results live", "caution"), ("Court verdict in bank scam case", "caution"), ("बाढ़ से तबाही", "sensitive"),
])
def test_sensitivity_levels(text, level):
    assert sensitivity.classify(text)["level"] == level


def test_advice_depends_on_who_you_are():
    assert sensitivity.advice("sensitive", "newsroom")["action"] == "care"
    assert sensitivity.advice("sensitive", "standard")["action"] == "avoid"
    assert sensitivity.advice("caution", "strict")["action"] == "avoid"
    assert sensitivity.advice("safe", "strict")["action"] == "go"


def test_newsroom_gets_sensitive_trend_with_care():
    org = Row(id=1, name="City News", category="news", window_hours=24, creator_type="news_channel", niche="", audience="",
              goals=["timeliness"], topics=[], formats=[], platforms=[], timezone=None, time_sensitive=None,
              region="IN", brand_safety=None)
    us = Row(id=1, name="City News", is_us=True, platform="youtube", subscribers=1, thumbnail=None, last_fetched_at=NOW)
    ds = Dataset(org, [us], [], now=NOW)
    row = TrendItem(id=1, org_id=1, key="k", source="google_trends", title="Flood in Chennai", traffic="100000+",
                    published_at=NOW, fetched_at=NOW, related=[])
    item = trends.build(ds, [row])[0]
    assert item["advice"]["action"] == "care" and "Verify" in item["advice"]["advice"]
    assert any("Explainer" in a for a in item["angles"])
    recs = recommend.trend_recs(ds, {}, [item])
    assert recs and "Verify" in recs[0]["next_step"]


# ---- Facebook comparison (unit) ----

def test_facebook_compare_engagement_per_follower():
    accs = [Row(id=1, name="Us", is_us=True, platform="facebook", subscribers=1000),
            Row(id=2, name="Them", is_us=False, platform="facebook", subscribers=1000)]

    def post(cid, i, likes, fmt):
        return Row(id=cid * 100 + i, competitor_id=cid, platform="facebook", title=f"p{i}", link=f"l{cid}{i}",
                   published_at=NOW - timedelta(days=2 + i), views=None, likes=likes, comments=0, shares=0,
                   format=fmt, duration_seconds=None, thumbnail=None)

    posts = [post(1, i, 10, "image") for i in range(6)] + [post(2, i, 40, "video") for i in range(10)]
    fb = compare(accs, posts, now=NOW)["platforms"]["facebook"]
    assert fb["us"]["engagement_rate"] == 1.0 and fb["market"]["engagement_rate"] == 4.0
    titles = [sg["title"] for sg in fb["suggestions"]]
    assert "Engagement per follower is low on Facebook" in titles and "Competitors post more videos" in titles


# ---- optional AI briefing (fake client: no network, no cost) ----

def test_ai_briefing_parses_caches_and_handles_refusal(monkeypatch):
    import anthropic

    import ai
    calls = []

    class FakeMessages:
        def __init__(self, stop="end_turn"):
            self.stop = stop

        def create(self, **kw):
            calls.append(kw)
            text = '{"summary": "Post more Reels.", "priorities": [], "content_ideas": []}'
            return Row(stop_reason=self.stop, model=kw["model"], content=[Row(type="text", text=text)])

    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: Row(messages=FakeMessages()))
    monkeypatch.setattr(ai, "_cache", {})
    out = ai.briefing(1, {"kpis": [1]})
    assert out["summary"] == "Post more Reels." and out["cached"] is False
    assert calls[0]["output_config"]["format"]["type"] == "json_schema" and calls[0]["extra_body"] == {"fallbacks": "default"}
    assert ai.briefing(1, {"kpis": [1]})["cached"] is True and len(calls) == 1  # same numbers -> no second call
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: Row(messages=FakeMessages("refusal")))
    with pytest.raises(ValueError, match="declined"):
        ai.briefing(1, {"kpis": [2]})


def test_careful_trend_gets_no_creative_angles():
    org = Row(id=2, name="Fit", category="fitness", window_hours=720, creator_type="influencer", niche="gym workouts",
              audience="", goals=[], topics=[], formats=[], platforms=[], timezone=None, time_sensitive=None,
              region="IN", brand_safety=None)
    ds = Dataset(org, [Row(id=1, name="Fit", is_us=True, platform="instagram", subscribers=1, thumbnail=None, last_fetched_at=NOW)], [], now=NOW)
    row = TrendItem(id=1, org_id=2, key="k", source="google_trends", title="gym trainer arrested", traffic="10000+",
                    published_at=NOW, fetched_at=NOW, related=[])
    item = trends.build(ds, [row])[0]
    assert item["advice"]["action"] == "care" and item["angles"] == [trends.CAREFUL_ANGLE]


def test_change_detector_handles_posts_without_views(client, bakery):
    """Instagram posts have a "vs usual" score from interactions but no views: the standout event must not crash."""
    r = client.get(f"/organizations/{bakery['id']}/changes")
    assert r.status_code == 200, r.text
    assert "interactions" in r.text
