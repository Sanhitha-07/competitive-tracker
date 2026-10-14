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
import meta
import recommend
import sensitivity
import trends
from dataset import Dataset
from db import engine
from models import TrendItem
from performance import compare

NOW = datetime.now(timezone.utc)


# ---- Meta parsing ----

@pytest.mark.parametrize("text,expected", [
    ("@Nike", "nike"), ("nike", "nike"), ("https://www.instagram.com/nike/", "nike"),
    ("instagram.com/the.bakery_co?igsh=abc", "the.bakery_co"),
])
def test_instagram_usernames(text, expected):
    assert meta.ig_username(text) == expected


def test_instagram_post_link_rejected():
    with pytest.raises(ValueError, match="post, not an account"):
        meta.ig_username("https://www.instagram.com/p/C0abc123/")


@pytest.mark.parametrize("text,expected", [
    ("https://www.facebook.com/nike", "nike"), ("facebook.com/profile.php?id=10001", "10001"),
    ("https://www.facebook.com/pages/Some-Cafe/123456789", "123456789"), ("@TheHindu", "TheHindu"),
])
def test_facebook_page_refs(text, expected):
    assert meta.fb_page_ref(text) == expected


def test_instagram_item_normalized():
    reel = meta.ig_item({"caption": "Diwali sweets box 🎁\nOrder now #diwali #Sweets", "comments_count": 12, "like_count": 300,
                         "view_count": 9000, "media_type": "VIDEO", "media_product_type": "REELS",
                         "permalink": "https://www.instagram.com/reel/x/", "timestamp": "2026-10-10T08:30:00+0000"})
    assert reel["format"] == "reel" and reel["views"] == 9000 and reel["tags"] == ["diwali", "sweets"]
    assert reel["title"] == "Diwali sweets box 🎁" and reel["published_at"].tzinfo is not None
    photo = meta.ig_item({"caption": "", "comments_count": 1, "media_type": "IMAGE", "media_product_type": "FEED",
                          "permalink": "https://www.instagram.com/p/y/", "timestamp": "2026-10-10T08:30:00+0000"})
    assert photo["format"] == "image" and photo["views"] is None and photo["likes"] is None  # hidden likes stay unknown
    assert photo["title"] == "(no caption)"


def test_facebook_item_normalized():
    item = meta.fb_item({"id": "1_2", "message": "New menu is here! #biryani", "created_time": "2026-10-11T10:00:00+0000",
                         "permalink_url": "https://www.facebook.com/1/posts/2", "attachments": {"data": [{"media_type": "photo"}]},
                         "shares": {"count": 4}, "reactions": {"summary": {"total_count": 120}}, "comments": {"summary": {"total_count": 9}}})
    assert (item["format"], item["likes"], item["comments"], item["shares"]) == ("image", 120, 9, 4)
    assert connectors.interactions(Row(**{k: item[k] for k in ("likes", "comments", "shares")})) == 133


def test_meta_needs_token(monkeypatch):
    monkeypatch.setattr(config, "META_ACCESS_TOKEN", "")
    with pytest.raises(meta.NotConfigured):
        meta.fb_find("nike")


def test_meta_budget_blocks_calls(monkeypatch):
    monkeypatch.setattr(config, "META_ACCESS_TOKEN", "t")
    monkeypatch.setattr(config, "META_HOURLY_BUDGET", 3)
    monkeypatch.setitem(meta._usage, "hour", meta._hour())
    monkeypatch.setitem(meta._usage, "calls", 3)
    with pytest.raises(meta.RateLimited):
        meta._get("me")


# ---- Instagram end to end through the API, with Meta replaced ----

def _bd(username, followers, n, likes, reels_every=3):
    media = [{"id": f"{username}{i}", "caption": f"{'Diwali sweets' if i % 2 else 'Fresh bread'} special #{username}",
              "comments_count": 5, "like_count": likes * (8 if (username == "rival1" and i == 1) else 1),
              "view_count": 5000 if i % reels_every == 0 else None,
              "media_type": "VIDEO" if i % reels_every == 0 else "IMAGE",
              "media_product_type": "REELS" if i % reels_every == 0 else "FEED",
              "permalink": f"https://www.instagram.com/p/{username}{i}/",
              "timestamp": (NOW - timedelta(days=3 + i * 2)).strftime("%Y-%m-%dT%H:%M:%S+0000")} for i in range(n)]
    return {"business_discovery": {"id": f"ig-{username}", "username": username, "name": username.title(),
                                   "followers_count": followers, "media_count": n, "profile_picture_url": None,
                                   "media": {"data": media}}}


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="module")
def bakery(client):
    accounts = {"ourbakery": (2000, 40), "rival1": (8000, 160), "rival2": (5000, 120)}
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "META_ACCESS_TOKEN", "test-token")
    mp.setattr(config, "META_IG_USER_ID", "17841")
    mp.setitem(meta._usage, "calls", 0)

    def fake_get(path, url=None, **params):
        user = params["fields"].split("business_discovery.username(")[1].split(")")[0]
        if user not in accounts:
            raise ValueError("Account not found, or it isn't a public Business/Creator account (personal accounts can't be read).")
        return _bd(user, accounts[user][0], 12, accounts[user][1])

    mp.setattr(meta, "_get", fake_get)
    r = client.post("/organizations", json={"name": "Sweet Spot Bakery", "creator_type": "small_business",
                                            "category": "restaurants", "niche": "bakery and sweets", "region": "IN"})
    assert r.status_code == 201, r.text
    org = r.json()
    for name, us in (("ourbakery", True), ("rival1", False), ("rival2", False)):
        r = client.post(f"/organizations/{org['id']}/accounts", json={"name": name, "platform": "instagram",
                                                                     "source": f"https://instagram.com/{name}/", "is_us": us})
        assert r.status_code == 201, r.text
        assert r.json()["source"] == f"@{name}" and r.json()["subscribers"] == accounts[name][0]
    bad = client.post(f"/organizations/{org['id']}/accounts", json={"name": "x", "platform": "instagram", "source": "@personal"})
    assert bad.status_code == 400 and "Business/Creator" in bad.json()["detail"]
    fetched = client.post(f"/organizations/{org['id']}/fetch").json()
    mp.undo()
    assert fetched["added"] == 36 and not any(a["error"] for a in fetched["accounts"])
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


def test_dashboard_explains_in_plain_language(client, bakery):
    d = client.get(f"/organizations/{bakery['id']}/dashboard").json()
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
