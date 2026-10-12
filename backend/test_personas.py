"""One app, many kinds of users. Run with:  python -m pytest -q

Builds made-up workspaces (fitness influencer, gaming streamer, educator, product brand,
news publisher) and checks that recommendations come from each one's own data and settings,
always carry their evidence, and never leak another niche's topics."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as Row

import pytest

import recommend
from dataset import Dataset
from performance import compare
from topics import STATUS_LABELS

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)

PERSONAS = {
    "fitness": dict(creator_type="influencer", platform="youtube", window=720,
                    theirs=["protein breakfast", "kettlebell workout", "mobility drills"],
                    ours=["kettlebell workout"], tracked=["mobility drills"],
                    niche="home strength training", audience="busy parents", goals=["grow_audience"],
                    formats=["short"], question="How much protein breakfast do I need after training?"),
    "gaming": dict(creator_type="streamer", platform="youtube", window=336,
                   theirs=["valorant ranked", "elden ring", "speedrun route"],
                   ours=["valorant ranked"], tracked=[], niche="competitive shooters", audience="teen gamers",
                   goals=["engagement"], formats=["live"], question="What sensitivity do you use for valorant ranked?"),
    "education": dict(creator_type="creator", platform="youtube", window=720,
                      theirs=["python decorators", "sql joins", "system design"],
                      ours=["python decorators"], tracked=["sql joins"], niche="programming tutorials",
                      audience="junior developers", goals=["authority"], formats=["long"],
                      question="Can you explain sql joins with a real example?"),
    "brand": dict(creator_type="brand", platform="youtube", window=720,
                  theirs=["skincare routine", "sunscreen review", "serum layering"],
                  ours=["skincare routine"], tracked=[], niche="skincare products", audience="women 25-40",
                  goals=["sales"], formats=["video"], question="Is this sunscreen review safe for oily skin?"),
    "news": dict(creator_type="publisher", platform="rss", window=24,
                 theirs=["monsoon flooding", "metro fares", "election results"],
                 ours=["metro fares"], tracked=[], niche="regional news", audience="city readers",
                 goals=["timeliness"], formats=["article"], question=None),
}

OTHER_TOPICS = {name: {t for p in PERSONAS.values() if p is not cfg for t in p["theirs"]}
                for name, cfg in PERSONAS.items()}


def build(name):
    p = PERSONAS[name]
    yt = p["platform"] == "youtube"
    org = Row(id=1, name=name, category=name if name != "brand" else "ecommerce", window_hours=p["window"],
              creator_type=p["creator_type"], niche=p["niche"], audience=p["audience"], goals=p["goals"],
              topics=p["tracked"], formats=p["formats"], platforms=[p["platform"]],
              timezone="Asia/Kolkata", time_sensitive=None)
    accounts = [Row(id=1, name="Our Account", is_us=True, platform=p["platform"], subscribers=1000, last_fetched_at=NOW)]
    accounts += [Row(id=i, name=f"Rival {i}", is_us=False, platform=p["platform"], subscribers=5000, last_fetched_at=NOW)
                 for i in (2, 3, 4)]
    hours = p["window"] / 10  # spread posts across the comparison window
    start = 50 if yt else 1  # video baselines need posts 48h+ old; news compares the last 24 hours
    posts, pid = [], 0

    def add(cid, title, age_h, views, fmt):
        nonlocal pid
        pid += 1
        posts.append(Row(id=pid, competitor_id=cid, platform=p["platform"], title=title, link=f"https://x.test/{pid}",
                         published_at=NOW - timedelta(hours=age_h), tags=[], thumbnail=None,
                         views=views if yt else None, likes=views // 20 if yt else None,
                         comments=views // 100 if yt else None, duration_seconds=600 if yt else None,
                         format=fmt, metrics_updated_at=NOW))

    for cid in (2, 3, 4):
        for i, topic in enumerate(p["theirs"] * 3):
            # each rival's 2nd post is an outlier: 6× its usual views
            add(cid, f"{topic} part {i}", start + i * hours / 2, 6000 if i == 1 else 1000, p["formats"][0] if yt else "article")
    for i, topic in enumerate(p["ours"] * 6):
        add(1, f"{topic} part {i}", start + i * hours / 2, 800, "video" if yt else "article")

    questions = []
    if p["question"]:
        questions = [Row(id=1, post_id=2, comment_id="c1", text=p["question"], likes=40, published_at=NOW - timedelta(days=1))]
    ds = Dataset(org, accounts, posts, questions, NOW)
    perf = compare(accounts, posts, now=NOW, tz=ds.tz)
    return ds, recommend.build(ds, perf)


@pytest.mark.parametrize("name", PERSONAS)
def test_topic_gaps_come_from_own_data(name):
    _, recs = build(name)
    gaps = {r["topic"] for r in recs if r["kind"] == "topic_gap"}
    missing = set(PERSONAS[name]["theirs"]) - set(PERSONAS[name]["ours"])
    assert missing <= gaps, f"{name}: expected {missing} in {gaps}"
    assert not gaps & set(PERSONAS[name]["ours"])


@pytest.mark.parametrize("name", PERSONAS)
def test_no_other_niche_leaks_in(name):
    _, recs = build(name)
    text = " ".join(r["title"] + r["observed"] for r in recs).lower()
    for other in OTHER_TOPICS[name]:
        assert other not in text, f"{name} recommendations mention {other!r}"


@pytest.mark.parametrize("name", PERSONAS)
def test_every_recommendation_explains_itself(name):
    _, recs = build(name)
    assert recs
    for r in recs:
        assert r["observed"] and r["why_relevant"] and r["next_step"]
        assert r["sample"]["text"]
        assert r["confidence"]["level"] in ("low", "medium", "high") and r["confidence"]["reason"]
        assert r["limitations"]
        assert "to" in r["data_period"]
        assert r["freshness"]["last_refresh"]


@pytest.mark.parametrize("name", [n for n, p in PERSONAS.items() if p["tracked"]])
def test_workspace_topics_rank_first(name):
    _, recs = build(name)
    gaps = [r for r in recs if r["kind"] == "topic_gap"]
    assert gaps[0]["topic"] == PERSONAS[name]["tracked"][0]
    assert "workspace topics" in gaps[0]["why_relevant"]


@pytest.mark.parametrize("name", [n for n, p in PERSONAS.items() if p["platform"] == "youtube"])
def test_outliers_found_relative_to_each_account(name):
    _, recs = build(name)
    outliers = [r for r in recs if r["kind"] == "outlier"]
    assert len(outliers) == 3  # one per rival
    assert all("6.0×" in r["title"] for r in outliers)


def test_news_feed_has_no_view_based_claims():
    ds, recs = build("news")
    assert not ds.relative
    assert not any(r["kind"] in ("outlier", "format_test") for r in recs)


@pytest.mark.parametrize("name", [n for n, p in PERSONAS.items() if p["question"]])
def test_audience_questions_are_used(name):
    _, recs = build(name)
    qs = [r for r in recs if r["kind"] == "audience_question"]
    assert qs and PERSONAS[name]["question"][:40] in qs[0]["title"]


def test_no_data_means_no_recommendations():
    org = Row(id=1, name="empty", category="fitness", window_hours=720, creator_type=None, niche=None,
              audience=None, goals=None, topics=None, formats=None, platforms=None, timezone=None, time_sensitive=None)
    acc = [Row(id=1, name="Us", is_us=True, platform="youtube", subscribers=None, last_fetched_at=None)]
    ds = Dataset(org, acc, [], [], NOW)
    perf = compare(acc, [], now=NOW)
    assert recommend.build(ds, perf) == []
    needs = recommend.readiness(ds, perf)
    assert any("workspace" in n for n in needs) and any("competitor" in n for n in needs)


def test_goal_changes_ranking_not_content():
    ds, base = build("gaming")
    ds.cfg["goals"] = ["community"]
    perf = compare(ds.accounts, ds.posts, now=NOW, tz=ds.tz)
    ranked = recommend.build(ds, perf)
    assert {r["key"] for r in ranked} == {r["key"] for r in base}
    assert ranked[0]["kind"] == "audience_question"


def test_never_claims_untapped():
    assert not any("untapped" in v.lower() for v in STATUS_LABELS.values())
    for name in PERSONAS:
        _, recs = build(name)
        assert not any("untapped" in (r["title"] + r["observed"]).lower() for r in recs)


def test_past_outcomes_are_shown_as_association():
    ds, _ = build("fitness")
    perf = compare(ds.accounts, ds.posts, now=NOW, tz=ds.tz)
    learned = {"topic_gap": {"evaluated": 4, "above": 3, "accepted": 4, "implemented": 4, "dismissed": 0}}
    recs = recommend.build(ds, perf, learned)
    note = next(r["past_results"] for r in recs if r["kind"] == "topic_gap")
    assert "3 of 4" in note and "not proof" in note


def test_branding_tags_are_not_topics_but_core_title_topics_are():
    from topics import coverage_map
    accounts = [Row(id=1, name="Us", is_us=True), Row(id=2, name="Rival", is_us=False), Row(id=3, name="Other", is_us=False)]
    posts = []
    for i in range(6):
        # Rival tags every video "hyderabad vlogs" (branding); we post only about kettlebells (core topic).
        posts.append(Row(id=i, competitor_id=2, title=f"day {i} kettlebell swing", tags=["hyderabad vlogs"], published_at=NOW))
        posts.append(Row(id=100 + i, competitor_id=1, title=f"kettlebell swing tips {i}", tags=[], published_at=NOW))
        posts.append(Row(id=200 + i, competitor_id=3, title=f"kettlebell swing form {i}", tags=["hyderabad vlogs"], published_at=NOW))
    rows, _ = coverage_map(posts, accounts)
    names = {r["topic"]: r for r in rows}
    assert "hyderabad vlogs" not in names
    assert names["kettlebell swing"]["our_posts"] == 6


def test_chitchat_questions_skipped_and_single_question_is_low_confidence():
    ds, _ = build("fitness")
    ds.questions.append(Row(id=2, post_id=2, comment_id="c2", text="What's her name di?", likes=900, published_at=NOW))
    perf = compare(ds.accounts, ds.posts, now=NOW, tz=ds.tz)
    qs = [r for r in recommend.build(ds, perf) if r["kind"] == "audience_question"]
    assert all("her name" not in r["title"] for r in qs)
    assert qs[0]["confidence"]["level"] == "low"
