"""Strategy experiments and the strategy simulator.

Simulator: strategies worth TESTING, each built from observations in the collected data, with its
sample size, effort, a suggested test length and the metric to watch. It never predicts views,
engagement or revenue: a strategy is a hypothesis, and an experiment is how it gets tested.

Experiment: hypothesis -> posts made for it -> result measured against a success rule set in
advance and against the user's own usual views. Results without enough posts are "inconclusive".
When the tracker can't measure a post (e.g. a website article, or a metric like sign-ups),
the user records the number, and it's labelled as entered by hand.
"""
import math
import re
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlmodel import select

import workspace
from dataset import iso, utc
from models import Post
from opportunities import normalize_link, views_at
from performance import engagement_rate

MEASURE_AFTER_DAYS = 7
TARGET_METRICS = {
    "views_vs_usual": {"label": "Views ÷ your usual views", "unit": "×", "auto": True,
                       "definition": "Each post's views 7 days after publishing ÷ your channel's usual (median) views."},
    "views": {"label": "Views after 7 days", "unit": "views", "auto": True,
              "definition": "Each post's public views about 7 days after publishing."},
    "engagement_rate": {"label": "Engagement rate", "unit": "%", "auto": True,
                        "definition": "(likes + comments) ÷ views at the last Refresh, for posts with public like counts."},
    "manual": {"label": "A number you record (e.g. sign-ups, clicks, page views)", "unit": "", "auto": False,
               "definition": "Entered by you for each post. The tracker can't check it."},
}
EDUCATIONAL = re.compile(r"\bhow to\b|\btutorial\b|\bguide\b|\bexplained\b|\bbeginners?\b|\bstep[- ]by[- ]step\b|\blearn\b", re.I)
EFFORT = {"short": ("low", "Short videos are quick to make."), "live": ("medium", "Needs scheduling and live presenting."),
          "video": ("medium", "A standard video takes scripting and editing."),
          "long": ("high", "Long-form videos take the most research and editing."),
          "article": ("medium", "Writing and editing an article.")}


# ---- evaluating an experiment ----

def _match(session, link, our_ids):
    if not our_ids or not link:
        return None
    return session.exec(select(Post).where(Post.competitor_id.in_(our_ids), Post.link == normalize_link(link))).first()


def evaluate(session, exp, ds):
    """Measure each post of the experiment and decide: successful, unsuccessful or inconclusive."""
    metric = exp.target_metric
    rows = []
    for link in exp.post_links or []:
        post = _match(session, link, list(ds.us_ids))
        row = {"link": link, "source": "tracker", "value": None}
        if not post:
            row["state"] = "not_found"
            row["note"] = "Not collected yet. Make sure your account is added as Ours, then Refresh."
        else:
            age = (ds.now - utc(post.published_at)).total_seconds() / 86400
            base = ds.baseline.get(post.competitor_id)
            row.update(title=post.title, published_at=iso(post.published_at))
            if metric == "manual":
                row["state"] = "manual_needed"
                row["note"] = "Record this post's number below."
            elif age < MEASURE_AFTER_DAYS:
                row["state"] = "too_new"
                row["note"] = f"Measured {MEASURE_AFTER_DAYS} days after publishing ({round(MEASURE_AFTER_DAYS - age, 1)} days to go)."
            elif post.views is None:
                row["state"] = "not_measurable"
                row["note"] = "This platform doesn't report views. Record a number by hand instead."
            else:
                views, at = views_at(session, post, MEASURE_AFTER_DAYS)
                row.update(views=views, measured_at=iso(at), baseline_views=round(base["median_views"]) if base else None,
                           vs_usual=round(views / base["median_views"], 2) if base and base["median_views"] else None)
                if metric == "views_vs_usual":
                    row["value"] = row["vs_usual"]
                elif metric == "views":
                    row["value"] = views
                elif metric == "engagement_rate" and post.likes is not None and post.views:
                    row["value"] = round((post.likes + (post.comments or 0)) / post.views * 100, 2)
                row["state"] = "measured" if row["value"] is not None else "not_measurable"
                if row["value"] is None:
                    row["note"] = ("No usual-views baseline yet (needs 5+ older posts)." if metric == "views_vs_usual"
                                   else "Like count is hidden, so engagement can't be calculated.")
        rows.append(row)
    for m in exp.manual_results or []:
        rows.append({"link": m.get("link"), "source": "manual", "value": m.get("value"), "state": "measured",
                     "note": m.get("note"), "recorded_at": m.get("at")})

    values = [r["value"] for r in rows if r["state"] == "measured" and r["value"] is not None]
    n = len(values)
    result = {"evaluated_at": iso(ds.now), "metric": metric, "threshold": exp.success_threshold,
              "min_posts": exp.min_posts, "measured_posts": n, "posts": rows,
              "median": round(median(values), 2) if values else None}
    ratios = [r["vs_usual"] for r in rows if r.get("vs_usual") is not None]
    result["median_vs_usual"] = round(median(ratios), 2) if ratios else None
    if n < exp.min_posts:
        result["state"] = "inconclusive"
        result["note"] = (f"{n} of the {exp.min_posts} posts needed have a result so far. "
                          "Wait for more posts to be published and measured before deciding.")
    elif result["median"] >= exp.success_threshold:
        result["state"] = "successful"
        result["note"] = (f"The median result ({result['median']}) met the goal you set ({exp.success_threshold}). "
                          f"Based on {n} posts: a good sign, not proof it will always work.")
    else:
        result["state"] = "unsuccessful"
        result["note"] = (f"The median result ({result['median']}) was below the goal you set ({exp.success_threshold}), "
                          f"over {n} posts. Other things (topic, timing) may have played a part.")
    return result


# ---- strategy simulator ----

def _posts_per_week(ds, days=90):
    since = ds.now - timedelta(days=days)
    ours = [p for p in ds.posts if ds.is_us(p) and utc(p.published_at) >= since]
    return len(ours) / days * 7, ours


def _duration(rate, posts_needed=3):
    if rate <= 0:
        return {"weeks": 4, "posts": posts_needed, "reason": f"{posts_needed} posts; no recent posting pace to base the length on."}
    weeks = min(max(math.ceil(posts_needed / rate) + 1, 2), 12)  # +1 week so the last post can be measured
    return {"weeks": weeks, "posts": posts_needed,
            "reason": f"{posts_needed} posts at your recent pace of {round(rate, 1)} a week, plus a week to measure the last one."}


def _rel(ds, posts):
    vals = [ds.relative[p.id] for p in posts if p.id in ds.relative]
    return (round(median(vals), 2) if vals else None), len(vals)


def strategies(ds, recs):
    rate, ours = _posts_per_week(ds)
    since = ds.now - timedelta(days=90)
    window = [p for p in ds.posts if utc(p.published_at) >= since]
    theirs = [p for p in window if not ds.is_us(p)]
    goals = [workspace.GOALS[g][0] for g in ds.cfg["goals"]]
    out = []

    def strategy(**kw):
        kw.setdefault("limitations", [])
        kw["limitations"].append("This is a hypothesis to test. No result is predicted.")
        kw["duration"] = _duration(rate, kw.pop("posts_needed", 3))
        out.append(kw)

    formats = {ds.format(p) for p in window if ds.format(p)}
    for f in sorted(formats):
        t_posts = [p for p in theirs if ds.format(p) == f]
        o_posts = [p for p in ours if ds.format(p) == f]
        t_med, t_n = _rel(ds, t_posts)
        o_med, o_n = _rel(ds, o_posts)
        t_acc = len({p.competitor_id for p in t_posts if p.id in ds.relative})
        share = len(o_posts) / len(ours) if ours else 0
        obs, why = [], None
        if t_med is not None and t_n >= 5 and t_acc >= 2 and t_med >= 1.2 and share < 0.2:
            obs.append(f"Competitors' {f} posts got a median {t_med}× their own usual views ({t_n} posts, {t_acc} accounts).")
            why = f"{f.capitalize()} posts do well for competitors, and you rarely use the format."
        if o_med is not None and o_n >= 3 and o_med >= 1.2 and share < 0.3:
            obs.append(f"Your own {f} posts got a median {o_med}× your usual views ({o_n} posts).")
            why = why or f"Your {f} posts already beat your usual, but they're a small share of what you publish."
        if not why:
            continue
        obs.append(f"{len(o_posts)} of your {len(ours)} posts in the last 90 days are {f} posts.")
        level, reason = EFFORT.get(f, ("medium", ""))
        strategy(id=f"format:{f}", title=f"Publish more {f} posts", why=why, observations=obs,
                 sample=f"{t_n} competitor and {o_n} of your posts with view data.",
                 effort={"level": level, "reason": reason},
                 hypothesis=f"Publishing more {f} posts will get more views relative to our usual than our other posts.",
                 variable_type="format", variable_value=f, metric="views_vs_usual", threshold=1.2,
                 limitations=["Formats differ in topic and effort too, so the format alone may not explain results."],
                 evidence=[ds.post_card(p) for p in sorted(t_posts, key=lambda p: -(ds.relative.get(p.id) or 0))[:3]])

    edu_t = [p for p in theirs if EDUCATIONAL.search(p.title)]
    other_t = [p for p in theirs if not EDUCATIONAL.search(p.title)]
    e_med, e_n = _rel(ds, edu_t)
    x_med, x_n = _rel(ds, other_t)
    edu_o = [p for p in ours if EDUCATIONAL.search(p.title)]
    if e_med is not None and e_n >= 4 and x_med is not None and e_med >= 1.2 and e_med - x_med >= 0.2:
        strategy(id="educational", title="Test educational (how-to) content",
                 why="Competitors' how-to and tutorial posts beat their usual views more than their other posts.",
                 observations=[f"Tutorial-style titles: median {e_med}× their usual ({e_n} posts).",
                               f"Other titles: median {x_med}× ({x_n} posts).",
                               f"{len(edu_o)} of your {len(ours)} recent posts have tutorial-style titles."],
                 sample=f"{e_n + x_n} competitor posts with view data.",
                 effort={"level": "medium", "reason": "Teaching content needs clear structure and examples."},
                 hypothesis="Beginner-friendly how-to posts will perform better for our audience than our usual posts.",
                 variable_type="topic", variable_value="how-to / tutorial", metric="views_vs_usual", threshold=1.2,
                 limitations=["Tutorial titles are found with English keywords (how to, guide, tutorial…)."],
                 evidence=[ds.post_card(p) for p in sorted(edu_t, key=lambda p: -(ds.relative.get(p.id) or 0))[:3]])

    gap = next((r for r in recs if r["kind"] == "topic_gap"), None)
    if gap:
        strategy(id=f"topic:{gap['topic'].lower()}", title=f'Cover "{gap["topic"]}"',
                 why=gap["why_relevant"], observations=[gap["observed"]], sample=gap["sample"]["text"],
                 effort={"level": "medium", "reason": "A topic that's new to you needs research."},
                 hypothesis=f'Posts about "{gap["topic"]}" will perform at least as well as our usual posts.',
                 variable_type="topic", variable_value=gap["topic"], metric="views_vs_usual", threshold=1.0,
                 limitations=gap["limitations"][:2], evidence=gap["evidence"]["posts"][:3], opportunity_key=gap["key"])

    qs = [r for r in recs if r["kind"] == "audience_question"]
    our_eng = engagement_rate([p for p in ours if ds.now - utc(p.published_at) >= timedelta(days=1)])
    if qs:
        strategy(id="questions", title="Answer common audience questions",
                 why="Viewers of the accounts you track are asking these in public comments.",
                 observations=[f'{len(qs)} question group(s) found, e.g. "{qs[0]["topic"]}".',
                               f"Your usual engagement rate: {our_eng}%." if our_eng is not None
                               else "Your engagement rate isn't available (no public like counts), so set a goal yourself."],
                 sample=qs[0]["sample"]["text"],
                 effort={"level": "low", "reason": "The question gives you the topic and the angle."},
                 hypothesis="Posts that answer audience questions will get more engagement than our usual posts.",
                 variable_type="topic", variable_value="audience questions", metric="engagement_rate",
                 threshold=our_eng, limitations=qs[0]["limitations"][:2], evidence=qs[0]["evidence"]["posts"][:2],
                 posts_needed=3)

    for s in out:
        s["metric_label"] = TARGET_METRICS[s["metric"]]["label"]
        s["goals"] = goals
    why_none = []
    if not out:
        if len(ours) < 3:
            why_none.append("You have fewer than 3 posts in the last 90 days, so there's no baseline to test against.")
        if len(theirs) < 10:
            why_none.append("Fewer than 10 competitor posts in the last 90 days. Add competitors or Refresh.")
        if not ds.baseline:
            why_none.append("No account has 5+ posts with view counts yet, so performance can't be compared.")
        if not why_none:
            why_none.append("Nothing in the data stands out strongly enough to suggest a test right now.")
    return {"strategies": out, "why_none": why_none, "posts_per_week": round(rate, 1)}


def now_utc():
    return datetime.now(timezone.utc)
