"""API checks on a throwaway database (see conftest.py). Run with:  python -m pytest -q
No internet needed: posts are inserted directly and the YouTube connector is replaced by a fake."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import connectors
import fetcher
import main
import youtube
from db import engine
from models import AudienceQuestion, Competitor, MetricSnapshot, Post

NOW = datetime.now(timezone.utc)


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def _org(client, name, **cfg):
    r = client.post("/organizations", json={"name": name, **cfg})
    assert r.status_code == 201, r.text
    return r.json()


def _seed(org_id):
    """Our YouTube channel + 3 competitors with 10 videos each; one competitor video is an outlier."""
    with Session(engine) as s:
        accs = [Competitor(org_id=org_id, name=n, platform="youtube", source=f"@{n}", is_us=(n == "Us"),
                           channel_id=f"UC{n}", subscribers=1000, last_fetched_at=NOW) for n in ("Us", "R1", "R2", "R3")]
        s.add_all(accs)
        s.commit()
        for a in accs:
            s.refresh(a)
            for i in range(10):
                topic = "kettlebell swing" if a.is_us else ["protein oats", "kettlebell swing", "mobility flow"][i % 3]
                s.add(Post(competitor_id=a.id, platform="youtube", title=f"{topic} part {i}",
                           link=f"https://www.youtube.com/watch?v={a.name}{i:08d}", published_at=NOW - timedelta(days=3 + i * 2),
                           views=9000 if (a.name == "R1" and i == 1) else 1000, likes=50, comments=5,
                           duration_seconds=45 if i % 2 else 600, format="short" if i % 2 else "video",
                           thumbnail="https://i.ytimg.com/x.jpg", tags=["fitness"]))
        s.commit()
        r1_post = s.exec(select(Post).join(Competitor).where(Competitor.name == "R1", Competitor.org_id == org_id)).first()
        s.add(AudienceQuestion(post_id=r1_post.id, comment_id=f"q{org_id}", text="How many protein oats per day is safe?",
                               likes=12, published_at=NOW - timedelta(days=1)))
        s.commit()
        return {a.name: a.id for a in accs}


# ---- workspace configuration ----

def test_create_workspace_with_config(client):
    org = _org(client, "Fit Studio", category="fitness", creator_type="influencer", niche="home workouts",
               audience="busy parents", goals=["grow_audience"], topics=["protein oats", " Protein Oats "],
               formats=["short"], timezone="Europe/London")
    assert org["category"] == "fitness" and org["window_hours"] == 720  # industry default
    cfg = client.get(f"/organizations/{org['id']}/config").json()
    assert cfg["topics"] == ["protein oats"]  # trimmed, duplicates removed
    assert cfg["configured"] and cfg["timezone"] == "Europe/London"


def test_legacy_category_still_accepted(client):
    org = _org(client, "Old Style News", category="News")
    assert org["category"] == "news" and org["window_hours"] == 24


@pytest.mark.parametrize("bad,msg", [
    ({"goals": ["get_rich"]}, "Unknown goals"),
    ({"formats": ["hologram"]}, "Unknown formats"),
    ({"timezone": "Mars/Base"}, "Unknown time zone"),
    ({"creator_type": "wizard"}, "creator/business type"),
    ({"category": "underwater"}, "industry"),
    ({"window_hours": 0}, "time window"),
    ({"topics": ["x" * 61]}, "too long"),
])
def test_config_validation(client, bad, msg):
    org_id = client.get("/organizations").json()[0]["id"]
    r = client.put(f"/organizations/{org_id}/config", json=bad)
    assert r.status_code == 400 and msg in r.json()["detail"]


def test_update_config_later(client):
    org = _org(client, "Gamer", category="gaming")
    r = client.put(f"/organizations/{org['id']}/config", json={"creator_type": "streamer", "topics": ["elden ring"], "goals": ["engagement"]})
    assert r.status_code == 200
    assert r.json()["config"]["topics"] == ["elden ring"]
    assert client.get(f"/organizations/{org['id']}/config").json()["creator_type"] == "streamer"


def test_options_describe_platform_metrics(client):
    o = client.get("/meta/options").json()
    yt = next(p for p in o["platforms"]["supported"] if p["id"] == "youtube")
    rss = next(p for p in o["platforms"]["supported"] if p["id"] == "rss")
    assert "relative_performance" in yt["metrics"] and "views" not in rss["metrics"]
    assert any(p["id"] == "instagram" for p in o["platforms"]["planned"])
    assert len(o["industries"]) >= 12


def test_unsupported_platform_rejected(client):
    org_id = client.get("/organizations").json()[0]["id"]
    r = client.post(f"/organizations/{org_id}/accounts", json={"name": "x", "platform": "myspace", "source": "x"})
    assert r.status_code == 400 and "not supported" in r.json()["detail"]


# ---- results, topics, explorer ----

@pytest.fixture(scope="module")
def seeded(client):
    org = _org(client, "Seeded Fitness", category="fitness", creator_type="creator", topics=["mobility flow"],
               goals=["community"], formats=["short"])
    return org["id"], _seed(org["id"])


def test_results_include_recommendations_with_evidence(client, seeded):
    org_id, _ = seeded
    d = client.get(f"/organizations/{org_id}/results").json()
    kinds = {r["kind"] for r in d["recommendations"]}
    assert {"topic_gap", "outlier", "audience_question"} <= kinds
    gap = next(r for r in d["recommendations"] if r["kind"] == "topic_gap" and r["topic"] == "mobility flow")
    assert gap["evidence"]["posts"] and gap["sample"]["competitor_posts"] >= 2 and gap["limitations"]
    assert d["overview"]["topics_to_review"] >= 2


def test_topic_map_marks_coverage(client, seeded):
    org_id, _ = seeded
    t = {x["topic"]: x for x in client.get(f"/organizations/{org_id}/topics").json()["topics"]}
    assert t["mobility flow"]["tracked"] and t["mobility flow"]["status"] == "not_covered_by_you"
    assert t["kettlebell swing"]["our_posts"] == 10
    assert t["protein oats"]["questions"] == 1
    assert "fitness" not in t or t["fitness"]["competitor_posts"] > 0


def test_explorer_filters(client, seeded):
    org_id, ids = seeded
    base = f"/organizations/{org_id}/content"
    all_ = client.get(base + "?limit=100").json()
    assert all_["total"] == 30  # competitors only by default
    assert all(not i["is_us"] for i in all_["items"])
    assert client.get(base + "?include_ours=true&limit=100").json()["total"] == 40
    assert client.get(base + f"?account_id={ids['R1']}").json()["total"] == 10
    assert client.get(base + "?format=short").json()["total"] == 15
    out = client.get(base + "?performance=outlier").json()
    assert out["total"] == 1 and out["items"][0]["relative"] == 9.0
    assert client.get(base + "?topic=protein%20oats").json()["total"] == 12
    assert client.get(base + "?q=mobility").json()["total"] > 0
    assert client.get(base + "?my_topics=true").json()["total"] == 9
    since = (NOW - timedelta(days=6)).isoformat()
    assert client.get(base, params={"since": since}).json()["total"] == 6
    top = client.get(base + "?sort=relative&limit=1").json()["items"][0]
    assert top["relative"] == 9.0 and top["thumbnail"] and top["topics"]


def test_explorer_my_topics_needs_config(client):
    org = _org(client, "No Topics", category="travel")
    r = client.get(f"/organizations/{org['id']}/content?my_topics=true")
    assert r.status_code == 400


# ---- opportunities: recommendation -> brief -> MediaOps -> scheduled -> published -> evaluated ----

def test_opportunity_lifecycle(client, seeded):
    org_id, ids = seeded
    base = f"/organizations/{org_id}/opportunities"
    listing = client.get(base).json()
    rec = next(r for r in listing["suggested"] if r["kind"] == "topic_gap")

    o = client.post(base, json={"key": rec["key"], "action": "brief"}).json()
    assert o["status"] == "brief" and o["snapshot"]["observed"] == rec["observed"]
    assert o["brief"]["references"] and "Don't reuse" in o["brief"]["originality_note"]
    assert client.post(base, json={"key": rec["key"]}).json()["id"] == o["id"]  # idempotent
    assert rec["key"] not in {r["key"] for r in client.get(base).json()["suggested"]}

    # MediaOps not configured: returns text to paste, status unchanged (nothing is approved or published here).
    m = client.post(f"{base}/{o['id']}/mediaops", json={"platforms": ["YouTube"]}).json()
    assert m["mode"] == "copy" and "Source: Competitive Tracker opportunity" in m["text"]
    assert m["opportunity"]["status"] == "brief"
    r = client.patch(f"{base}/{o['id']}", json={"status": "in_mediaops", "mediaops_ref": "DP-123"})
    assert r.json()["status"] == "in_mediaops" and r.json()["mediaops_ref"] == "DP-123"

    assert client.patch(f"{base}/{o['id']}", json={"status": "scheduled"}).status_code == 400  # needs a date
    when = (NOW + timedelta(days=2)).isoformat()
    assert client.patch(f"{base}/{o['id']}", json={"status": "scheduled", "planned_for": when}).json()["status"] == "scheduled"
    ics = client.get(f"{base}/{o['id']}/calendar.ics")
    assert ics.status_code == 200 and "BEGIN:VEVENT" in ics.text and ics.headers["content-type"].startswith("text/calendar")
    assert all(len(line) <= 75 for line in ics.text.split("\r\n"))

    assert client.patch(f"{base}/{o['id']}", json={"status": "published"}).status_code == 400  # needs a link
    assert client.patch(f"{base}/{o['id']}", json={"published_link": "not a link"}).status_code == 400

    # Our published post, 8 days old, 2,000 views at day 7 vs our usual 1,000.
    with Session(engine) as s:
        post = Post(competitor_id=ids["Us"], platform="youtube", title="mobility flow for parents",
                    link="https://www.youtube.com/watch?v=OURVIDEO01", published_at=NOW - timedelta(days=8),
                    views=2600, likes=100, comments=10, duration_seconds=50, format="short", metrics_updated_at=NOW)
        s.add(post)
        s.commit()
        s.refresh(post)
        s.add(MetricSnapshot(post_id=post.id, captured_at=NOW - timedelta(hours=20), views=2000))
        s.commit()
    r = client.patch(f"{base}/{o['id']}", json={"status": "published", "published_link": "https://youtu.be/OURVIDEO01"})
    assert r.json()["status"] == "published"

    result = client.post(f"{base}/{o['id']}/evaluate").json()
    assert result["state"] == "evaluated" and result["views"] == 2000 and result["ratio"] == 2.0
    assert result["verdict"] == "above_usual" and "doesn't show" in result["note"]

    tracked = next(t for t in client.get(base).json()["tracked"] if t["id"] == o["id"])
    assert tracked["status"] == "evaluated"
    assert [h["status"] for h in tracked["history"]] == ["saved", "brief", "in_mediaops", "scheduled", "published", "evaluated"]
    learned = client.get(base).json()["learned"]["topic_gap"]
    assert learned["implemented"] == 1 and learned["evaluated"] == 1 and learned["above"] == 1


def test_young_post_is_still_measuring(client, seeded):
    org_id, ids = seeded
    base = f"/organizations/{org_id}/opportunities"
    rec = next(r for r in client.get(base).json()["suggested"] if r["kind"] == "outlier")
    o = client.post(base, json={"key": rec["key"]}).json()
    with Session(engine) as s:
        s.add(Post(competitor_id=ids["Us"], platform="youtube", title="new one", link="https://www.youtube.com/watch?v=OURVIDEO02",
                   published_at=NOW - timedelta(days=2), views=500, format="video"))
        s.commit()
    client.patch(f"{base}/{o['id']}", json={"published_link": "https://www.youtube.com/watch?v=OURVIDEO02"})
    client.patch(f"{base}/{o['id']}", json={"status": "brief"})
    client.patch(f"{base}/{o['id']}", json={"status": "published"})
    assert client.post(f"{base}/{o['id']}/evaluate").json()["state"] == "measuring"


def test_invalid_transition_rejected(client, seeded):
    org_id, _ = seeded
    base = f"/organizations/{org_id}/opportunities"
    rec = next(r for r in client.get(base).json()["suggested"])
    o = client.post(base, json={"key": rec["key"]}).json()
    r = client.patch(f"{base}/{o['id']}", json={"status": "evaluated"})
    assert r.status_code == 400 and "Can't move" in r.json()["detail"]


def test_stale_recommendation_key(client, seeded):
    org_id, _ = seeded
    r = client.post(f"/organizations/{org_id}/opportunities", json={"key": "topic_gap:no-such-topic"})
    assert r.status_code == 404


def test_history_endpoints(client, seeded):
    org_id, _ = seeded
    h = client.get(f"/organizations/{org_id}/history").json()
    us = next(a for a in h["accounts"] if a["is_us"])
    assert us["weekly"] and us["baseline"]["posts"] >= 5
    assert h["our_recent_vs_baseline"]


# ---- fetcher: snapshots, backfill, quota ----

class FakeYouTube(connectors.YouTubeConnector):
    def __init__(self, views=100, quota_on_questions=False):
        self.views, self.quota_on_questions = views, quota_on_questions

    def fetch(self, account):
        account.subscribers = 5000
        return [{"title": "fake video", "link": "https://www.youtube.com/watch?v=FAKE0000001",
                 "published_at": NOW - timedelta(days=1), "views": self.views, "likes": 1, "comments": 3,
                 "duration_seconds": 30, "thumbnail": "t.jpg", "tags": ["a"], "format": "short"}]

    def questions(self, post):
        if self.quota_on_questions:
            raise youtube.QuotaExceeded("quota")
        return [{"comment_id": "fq1", "text": "Which shoes are you wearing in this?", "likes": 2, "published_at": NOW}]


def test_fetch_saves_snapshots_questions_and_handles_quota(client, monkeypatch):
    org = _org(client, "Fetch Test", category="fitness")
    with Session(engine) as s:
        a = Competitor(org_id=org["id"], name="Chan", platform="youtube", source="@chan", is_us=False)
        s.add(a)
        s.commit()
        monkeypatch.setitem(connectors.CONNECTORS, "youtube", FakeYouTube(views=100))
        res = fetcher.fetch_org(s, org["id"], now=NOW)
        assert res["added"] == 1 and res["accounts"][0]["questions"] == 1 and res["accounts"][0]["snapshots"] == 1

        # Second refresh soon after: metrics updated, no duplicate snapshot within 6 hours.
        monkeypatch.setitem(connectors.CONNECTORS, "youtube", FakeYouTube(views=250, quota_on_questions=True))
        res = fetcher.fetch_org(s, org["id"], now=NOW + timedelta(hours=1))
        assert res["added"] == 0 and res["accounts"][0]["snapshots"] == 0 and res["accounts"][0]["error"] is None
        post = s.exec(select(Post).where(Post.competitor_id == a.id)).one()
        assert post.views == 250

        # Later refresh: new snapshot. Quota error on comments doesn't lose the posts.
        res = fetcher.fetch_org(s, org["id"], now=NOW + timedelta(hours=8))
        assert res["accounts"][0]["snapshots"] == 1
        assert len(s.exec(select(MetricSnapshot).where(MetricSnapshot.post_id == post.id)).all()) == 2


def test_quota_budget_blocks_calls(monkeypatch):
    monkeypatch.setattr(youtube, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(youtube, "YOUTUBE_DAILY_BUDGET", 50)
    youtube.units_used()
    monkeypatch.setitem(youtube._usage, "units", 0)
    with pytest.raises(youtube.QuotaExceeded):
        youtube._get("search", q="x")  # 100 units > budget, refused before calling the API
