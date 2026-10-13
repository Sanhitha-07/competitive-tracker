"""Checks for the dashboard, topic corrections, priorities, collections, change feed, Content DNA,
experiments and the duplicate-draft guard. Run with:  python -m pytest -q
Uses the throwaway database from conftest.py; no internet needed."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as Row

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

import main
from db import engine
from models import AccountSnapshot, Competitor, Post
from performance import account_stats, compare

NOW = datetime.now(timezone.utc)


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def _post(acc, i, title, days_ago, views=1000, likes=50, fmt="video", platform="youtube", tags=None):
    return Post(competitor_id=acc.id, platform=platform, title=title,
                link=f"https://www.youtube.com/watch?v={acc.id:03d}{i:08d}" if platform == "youtube" else f"https://site{acc.id}.test/{i}",
                published_at=NOW - timedelta(days=days_ago), views=views if platform == "youtube" else None,
                likes=likes if platform == "youtube" else None, comments=5 if platform == "youtube" else None,
                duration_seconds=600 if platform == "youtube" else None, format=fmt if platform == "youtube" else "article",
                tags=tags or [], metrics_updated_at=NOW if platform == "youtube" else None)


@pytest.fixture(scope="module")
def org(client):
    r = client.post("/organizations", json={"name": "Enh Fitness", "category": "fitness", "creator_type": "creator",
                                            "niche": "kettlebell training", "goals": ["grow_audience"], "topics": ["mobility"]})
    org_id = r.json()["id"]
    with Session(engine) as s:
        us = Competitor(org_id=org_id, name="Us", platform="youtube", source="@us", is_us=True, channel_id="UCus", last_fetched_at=NOW)
        site = Competitor(org_id=org_id, name="Us", platform="rss", source="https://us.test/feed", is_us=True, last_fetched_at=NOW)
        r1 = Competitor(org_id=org_id, name="Rival One", platform="youtube", source="@r1", channel_id="UCr1", last_fetched_at=NOW)
        r2 = Competitor(org_id=org_id, name="Rival Two", platform="youtube", source="@r2", channel_id="UCr2", last_fetched_at=NOW)
        s.add_all([us, site, r1, r2])
        s.commit()
        for a in (us, site, r1, r2):
            s.refresh(a)
        posts = []
        # Ours: 8 videos on kettlebell (usual) and 3 on "protein oats" that do badly (0.3× usual).
        for i in range(8):
            posts.append(_post(us, i, f"kettlebell swing lesson {i}", 3 + i * 5, views=1000))
        for i in range(3):
            posts.append(_post(us, 20 + i, f"protein oats breakfast {i}", 4 + i * 6, views=300))
        for i in range(4):
            posts.append(_post(site, i, f"Blog: kettlebell grip guide {i}", 2 + i * 4, platform="rss"))
        # Rivals: protein oats + "whey shake" posts; Rival One has a 6× standout this week.
        for acc in (r1, r2):
            for i in range(14):
                title = ["protein oats recipe", "whey shake review", "mobility flow"][i % 3] + f" {i}"
                views = 6000 if (acc is r1 and i == 0) else 1000
                posts.append(_post(acc, i, title, 3 + i * 4, views=views, likes=None if acc is r2 else 40,
                                   fmt="short" if i % 2 else "video"))
        s.add_all(posts)
        s.add(AccountSnapshot(competitor_id=r1.id, captured_at=NOW - timedelta(days=28), subscribers=10000))
        s.add(AccountSnapshot(competitor_id=r1.id, captured_at=NOW, subscribers=12000))
        s.commit()
        return {"id": org_id, "us": us.id, "site": site.id, "r1": r1.id, "r2": r2.id}


# ---- missing metrics are not zero ----

def test_missing_metrics_are_none_not_zero():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    vids = [Row(competitor_id=1, title="x", link="l", published_at=now - timedelta(days=d), views=100, likes=None,
                comments=None, duration_seconds=None, format="video") for d in (2, 3, 4)]
    stats = account_stats(vids, now)
    assert stats["engagement_rate"] is None  # hidden likes: unknown, not 0%
    assert stats["avg_length_seconds"] is None and stats["shorts_pct"] is None
    acc = [Row(id=1, name="Us", is_us=True, platform="youtube", subscribers=None),
           Row(id=2, name="R", is_us=False, platform="youtube", subscribers=None)]
    result = compare(acc, vids + [Row(**{**vars(v), "competitor_id": 2}) for v in vids], now=now)
    assert result["market"]["engagement_rate"] is None
    assert not any(s["metric"] == "engagement_rate" for s in result["suggestions"])


# ---- dashboard ----

def test_dashboard_keeps_youtube_and_website_apart(client, org):
    d = client.get(f"/organizations/{org['id']}/dashboard?days=90").json()
    assert d["youtube"]["items"] and all(p["platform"] == "youtube" for p in d["youtube"]["items"])
    assert d["website"]["items"] and all(p["platform"] == "rss" for p in d["website"]["items"])
    assert d["website"]["metrics_available"] is False
    assert all(p["views"] is None for p in d["website"]["items"])  # never shown as 0
    keys = {m["key"] for m in d["summary"]}
    assert {"per_week_youtube", "per_week_rss", "typical_views", "engagement"} <= keys


def test_dashboard_trend_has_gaps_not_zeros(client, org):
    d = client.get(f"/organizations/{org['id']}/dashboard?days=365").json()
    views = d["trend"]["series"]["views"]
    ours = next(s for s in views if s["account_id"] == org["us"])
    # Weeks without our videos have no point (None), not 0 views.
    assert any(p["y"] is None for p in ours["points"])
    assert all(p["y"] is None or p["y"] > 0 for p in ours["points"])
    posts = next(s for s in d["trend"]["series"]["posts_youtube"] if s["account_id"] == org["us"])
    first = next(i for i, p in enumerate(posts["points"]) if p["y"] is not None)
    assert all(p["y"] is None for p in posts["points"][:first])  # nothing before we knew the account
    assert "subscribers" in d["trend"]["series"]


def test_dashboard_filters_apply_everywhere(client, org):
    d = client.get(f"/organizations/{org['id']}/dashboard", params={"days": 90, "topic": "kettlebell"}).json()
    assert all("kettlebell" in p["title"].lower() for p in d["youtube"]["items"] + d["website"]["items"])
    comp = client.get(f"/organizations/{org['id']}/dashboard", params={"competitor_id": org["r1"]}).json()
    names = {s["name"] for s in comp["trend"]["series"]["posts_youtube"]}
    assert "Rival Two" not in names and "Rival One" in names
    assert client.get(f"/organizations/{org['id']}/dashboard", params={"competitor_id": 99999}).status_code == 404


# ---- topics: underperforming, grouping, corrections ----

def test_topic_underperforming_and_reason(client, org):
    topics = client.get(f"/organizations/{org['id']}/topics", params={"days": 90}).json()["topics"]
    oats = next(t for t in topics if t["topic"] == "protein oats")
    assert oats["status"] == "covered_underperforming" and oats["our_median_relative"] < 0.8
    assert oats["opportunity"] and "your usual" in oats["reason"]
    assert all("group" in t for t in topics)


def test_topic_corrections_merge_and_exclude(client, org):
    url = f"/organizations/{org['id']}"
    r = client.put(f"{url}/config", json={"topic_rules": {"aliases": {"whey shake": "Protein drinks"}, "excluded": ["review"]}})
    assert r.status_code == 200
    topics = client.get(f"{url}/topics", params={"days": 90}).json()["topics"]
    names = {t["topic"] for t in topics}
    assert "Protein drinks" in names and "whey shake" not in names and "review" not in names
    assert next(t for t in topics if t["topic"] == "Protein drinks")["renamed"]
    client.put(f"{url}/config", json={"topic_rules": {"aliases": {}, "excluded": []}})


# ---- priorities and briefs on demand ----

def test_recommendations_have_explained_priority(client, org):
    recs = client.get(f"/organizations/{org['id']}/recommendations").json()["recommendations"]
    actionable = [r for r in recs if r["actionable"]]
    assert actionable
    for r in actionable:
        assert r["priority"]["level"] in ("high", "medium", "low") and r["priority"]["reasons"]
        if r["confidence"]["level"] == "low":
            assert r["priority"]["level"] != "high"
    assert not any(k.startswith("_") for r in recs for k in r)


def test_brief_from_topic_and_post_without_duplicates(client, org):
    url = f"/organizations/{org['id']}/opportunities"
    a = client.post(url, json={"topic": "mobility flow", "action": "brief"})
    b = client.post(url, json={"topic": "Mobility Flow", "action": "brief"})
    assert a.status_code == 201 and a.json()["id"] == b.json()["id"] and a.json()["brief"]
    with Session(engine) as s:
        standout = s.exec(main.select(Post).where(Post.competitor_id == org["r1"], Post.views == 6000)).first()
    p1 = client.post(url, json={"post_id": standout.id, "action": "brief"}).json()
    assert p1["key"] == f"outlier:{standout.id}"  # same opportunity as the automatic suggestion
    assert client.post(url, json={"topic": "no such topic at all"}).status_code == 404


def test_duplicate_mediaops_draft_blocked(client, org):
    url = f"/organizations/{org['id']}/opportunities"
    o = client.post(url, json={"topic": "whey shake", "action": "brief"}).json()
    client.patch(f"{url}/{o['id']}", json={"status": "in_mediaops", "mediaops_ref": "DP-77"})
    r = client.post(f"{url}/{o['id']}/mediaops", json={"platforms": ["YouTube"]})
    assert r.status_code == 409 and "DP-77" in r.json()["detail"]
    assert client.patch(f"{url}/{o['id']}", json={"status": "completed"}).json()["status"] == "completed"


# ---- collections ----

def test_collections_save_filter_remove(client, org):
    url = f"/organizations/{org['id']}"
    post_id = client.get(f"{url}/content").json()["items"][0]["id"]
    a = client.post(f"{url}/collections/items", json={"collection": "Content Ideas", "post_id": post_id}).json()
    b = client.post(f"{url}/collections/items", json={"collection": "Content Ideas", "post_id": post_id}).json()
    assert a["id"] == b["id"]
    items = client.get(f"{url}/content", params={"collection": "Content Ideas"}).json()["items"]
    assert [p["id"] for p in items] == [post_id] and items[0]["saved_in"][0]["collection"] == "Content Ideas"
    assert client.delete(f"{url}/collections/items/{a['id']}").status_code == 204
    assert client.get(f"{url}/content", params={"collection": "Content Ideas"}).json()["total"] == 0
    assert client.post(f"{url}/collections/items", json={"collection": "X", "post_id": 999999}).status_code == 404


def test_engagement_sort_puts_unknown_last(client, org):
    items = client.get(f"/organizations/{org['id']}/content", params={"sort": "engagement", "limit": 100}).json()["items"]
    known = [p["engagement_rate"] is not None for p in items]
    assert known == sorted(known, reverse=True)  # all known values first


# ---- change detector ----

def test_changes_listed_once_and_status_kept(client, org):
    url = f"/organizations/{org['id']}/changes"
    first = client.get(url).json()
    kinds = {c["kind"] for c in first["changes"]}
    assert "standout" in kinds and "audience" in kinds
    again = client.get(url).json()
    assert len(again["changes"]) == len(first["changes"])  # no duplicates on re-check
    cid = first["changes"][0]["id"]
    assert client.patch(f"{url}/{cid}", json={"status": "reviewed"}).json()["status"] == "reviewed"
    assert next(c for c in client.get(url).json()["changes"] if c["id"] == cid)["status"] == "reviewed"


# ---- Content DNA ----

def test_content_dna_profile(client, org):
    d = client.get(f"/organizations/{org['id']}/dna", params={"account_id": org["r1"]}).json()
    p = d["profiles"][0]
    assert p["posts"] == 14 and p["enough_data"]
    assert {t["topic"] for t in p["main_topics"]} & {"protein oats", "whey shake", "mobility flow"}
    assert p["standout_count"] >= 1 and p["summary"]
    assert len(client.get(f"/organizations/{org['id']}/dna").json()["profiles"]) == 4


# ---- experiments ----

def test_experiment_lifecycle(client, org):
    url = f"/organizations/{org['id']}/experiments"
    listing = client.get(url).json()
    assert "strategies" in listing["simulator"] and listing["metrics"]
    e = client.post(url, json={"hypothesis": "Kettlebell lessons beat our usual", "target_metric": "views_vs_usual",
                               "success_threshold": 1.2, "min_posts": 2}).json()
    assert e["status"] == "planned"
    assert client.patch(f"{url}/{e['id']}", json={"status": "completed"}).status_code == 400  # must run first
    assert client.patch(f"{url}/{e['id']}", json={"status": "running"}).json()["started_at"]
    new = "https://www.youtube.com/watch?v=" + f"{org['us']:03d}{0:08d}"   # 3 days old
    old = "https://www.youtube.com/watch?v=" + f"{org['us']:03d}{2:08d}"   # 13 days old
    client.patch(f"{url}/{e['id']}", json={"add_post_link": new})
    client.patch(f"{url}/{e['id']}", json={"add_post_link": old})
    r = client.post(f"{url}/{e['id']}/evaluate").json()["result"]
    states = {p["link"]: p["state"] for p in r["posts"]}
    assert states[new] == "too_new" and states[old] == "measured"
    assert r["state"] == "inconclusive" and r["measured_posts"] == 1  # 1 of 2 posts
    client.patch(f"{url}/{e['id']}", json={"add_manual_result": {"value": 2.0, "note": "from analytics"}})
    r = client.post(f"{url}/{e['id']}/evaluate").json()["result"]
    assert r["measured_posts"] == 2 and r["state"] in ("successful", "unsuccessful")
    assert any(p["source"] == "manual" for p in r["posts"])
    assert client.patch(f"{url}/{e['id']}", json={"add_manual_result": {"value": "lots"}}).status_code == 400
    assert client.delete(f"{url}/{e['id']}").status_code == 204


# ---- accounts and workspace ----

def test_account_edit_group_and_health(client, org):
    url = f"/organizations/{org['id']}/accounts"
    r = client.patch(f"{url}/{org['r2']}", json={"name": "Rival Two Renamed", "group": "aspirational"})
    assert r.status_code == 200 and r.json()["group"] == "aspirational"
    assert client.patch(f"{url}/{org['r2']}", json={"group": "frenemy"}).status_code == 400
    assert client.patch(f"{url}/{org['us']}", json={"group": "direct"}).status_code == 400
    rows = {a["id"]: a for a in client.get(url).json()}
    assert rows[org["r2"]]["group_label"] == "Aspirational"
    assert rows[org["us"]]["public_url"] == "https://www.youtube.com/channel/UCus"
    assert rows[org["r1"]]["health"]["state"] == "ok"
    client.patch(f"{url}/{org['r2']}", json={"name": "Rival Two", "group": None})


def test_workspace_rename_and_sub_niche(client, org):
    url = f"/organizations/{org['id']}/config"
    r = client.put(url, json={"name": "Enh Fitness Studio", "sub_niche": "kettlebells for beginners"})
    assert r.status_code == 200 and r.json()["organization"]["name"] == "Enh Fitness Studio"
    assert r.json()["config"]["sub_niche"] == "kettlebells for beginners"
    client.post("/organizations", json={"name": "Taken Name"})
    assert client.put(url, json={"name": "Taken Name"}).status_code == 400
