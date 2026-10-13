"""Niche-aware recommendations built only from collected data.

Every recommendation says what was observed, why it matters to THIS workspace, the evidence
(posts, questions, metrics), the data period, the sample size, a confidence level with its reason,
and its limitations. Nothing is shown when there is no data to back it: no generic advice.

The workspace configuration (topics, niche, audience, goals, formats) only RANKS and EXPLAINS
recommendations; it never invents one. Past outcomes of similar recommendations adjust ranking
a little and are shown as an association, not a cause.
"""
from collections import defaultdict
from statistics import median

from rapidfuzz import fuzz

import textutil
import workspace
from connectors import CONNECTORS, METRICS
from dataset import OUTLIER_RATIO, iso, utc
from performance import MIN_VIDEOS, PERF_DAYS
from topics import STATUS_LABELS, STOPWORDS

MAX_PER_KIND = 6
FORMAT_MIN_POSTS = 5          # posts needed in a format before comparing it
FORMAT_LIFT = 1.2             # format's median relative performance must be ≥ 1.2× to suggest testing
QUESTION_MIN_LIKES = 1
QUESTION_MIN_WORDS = 3        # words of 3+ letters that aren't stopwords


def _content_words(text):
    return sum(1 for w in textutil.words(text) if len(w) >= 3 and w not in STOPWORDS)

KIND_LABELS = {
    "topic_gap": "Topic competitors cover",
    "audience_question": "Audience question",
    "outlier": "Unusually strong competitor post",
    "format_test": "Format worth testing",
    "publishing_pattern": "Publishing pattern to investigate",
    "benchmark": "Benchmark",
}
ACTIONABLE = {"topic_gap", "audience_question", "outlier", "format_test"}
CONFIDENCE_WEIGHT = {"high": 1.0, "medium": 0.85, "low": 0.7}


def _format_label(f):
    return workspace.FORMATS.get(f, (f or "Any format",))[0]


def _relevance_words(cfg):
    text = " ".join([cfg["niche"], cfg["audience"], cfg["industry_label"] if cfg["industry"] != "other" else ""])
    return {w for w in textutil.words(text) if len(w) >= 3 and w not in STOPWORDS}


def _relevance(cfg, text, words):
    """(score multiplier, reason) for how well a text matches the workspace configuration."""
    low = text.lower()
    for t in cfg["topics"]:
        if textutil.contains_phrase(low, t):
            return 1.6, f'Matches "{t}", one of your workspace topics.'
    hit = sorted(w for w in words if textutil.contains_phrase(low, w))
    if hit:
        return 1.3, f"Mentions {', '.join(hit[:3])} from your niche/audience description."
    return 1.0, None


def _confidence(level, reason):
    return {"level": level, "reason": reason}


def _outcome_note(kind, learned):
    s = learned.get(kind)
    if not s or s["evaluated"] < 3:
        return None, 1.0
    rate = s["above"] / s["evaluated"]
    note = (f"Your past results for this kind of recommendation: {s['above']} of {s['evaluated']} "
            f"published posts beat your usual views. That's an association, not proof it caused the result.")
    return note, 0.8 + 0.4 * rate


def _finish(rec, ds, learned):
    note, w = _outcome_note(rec["kind"], learned)
    if note:
        rec["past_results"] = note
    rec["weight"] = workspace.goal_weight(ds.cfg, rec["kind"]) * w * CONFIDENCE_WEIGHT[rec["confidence"]["level"]]
    rec["kind_label"] = KIND_LABELS[rec["kind"]]
    rec["actionable"] = rec["kind"] in ACTIONABLE
    rec["freshness"] = ds.freshness()
    rec.setdefault("data_period", ds.period())
    return rec


def _best_format(ds, posts):
    """The format competitors used most for these posts, preferring the user's preferred formats."""
    counts = defaultdict(int)
    for p in posts:
        if ds.format(p):
            counts[ds.format(p)] += 1
    if not counts:
        return None
    preferred = [f for f in ds.cfg["formats"] if counts.get(f)]
    if preferred:
        return max(preferred, key=lambda f: counts[f])
    return max(counts, key=counts.get)


# ---- 1. topics competitors cover that we don't (or cover less) ----

def topic_recs(ds, learned):
    rows, our_total = ds.topics()
    words = _relevance_words(ds.cfg)
    out = []
    for t in rows:
        if t["status"] not in ("not_covered_by_you", "covered_less") or t["competitor_posts"] < 2:
            continue
        posts = [ds.post_by_id[i] for i in t["post_ids"] if not ds.is_us(ds.post_by_id[i])]
        rel_score, reason = _relevance(ds.cfg, t["topic"] + " " + " ".join(p.title for p in posts[:5]), words)
        if t["tracked"]:
            reason = f'"{t["topic"]}" is one of your workspace topics.'
            rel_score = 1.8
        lift = 1.2 if (t["median_relative"] or 0) >= 1.2 else 1.0
        n_comp = len(t["competitors"])
        limitations = [
            "Topics are found by matching words in titles and tags. You may have covered this under different wording.",
            f"Only posts from {iso(ds.since)[:10]} onward and the latest posts each account's feed returns are included.",
        ]
        if t["confidence"] == "low":
            limitations.append("Small sample: treat this as a lead to check, not a conclusion.")
        fmt = _best_format(ds, posts)
        observed = (f'{n_comp} competitor{"s" if n_comp != 1 else ""} published {t["competitor_posts"]} post'
                    f'{"s" if t["competitor_posts"] != 1 else ""} about "{t["topic"]}"; you published {t["our_posts"]}.')
        if t["median_relative"] is not None:
            observed += f' Their typical post on it got {t["median_relative"]}× their usual views (from {t["relative_sample"]} posts with view data).'
        out.append({
            "key": f"topic_gap:{t['topic'].lower()}",
            "kind": "topic_gap",
            "tone": "lagging" if t["status"] == "not_covered_by_you" else "info",
            "title": f'{STATUS_LABELS[t["status"]]}: "{t["topic"]}"',
            "topic": t["topic"],
            "observed": observed,
            "detail": observed,
            "why_relevant": reason or f"Covered by {n_comp} of the competitors you chose to track in this workspace.",
            "evidence": {
                "posts": [ds.post_card(p) for p in sorted(posts, key=lambda p: ds.relative.get(p.id) or 0, reverse=True)[:6]],
                "questions": [ds.question_card(q) for q in ds.questions
                              if textutil.contains_phrase(q.text, t["topic"])][:5],
                "metrics": [m for m in [
                    {"label": "Competitor posts on topic", "value": t["competitor_posts"]},
                    {"label": "Your posts on topic", "value": t["our_posts"]},
                    {"label": "Competitors covering it", "value": n_comp},
                    t["median_relative"] is not None and {
                        "label": "Their typical relative performance", "value": f'{t["median_relative"]}×',
                        "definition": METRICS["relative_performance"]},
                ] if m],
            },
            "sample": {"competitor_posts": t["competitor_posts"], "competitor_accounts": n_comp,
                       "your_posts_checked": our_total,
                       "text": f'{t["competitor_posts"]} competitor posts from {n_comp} account{"s" if n_comp != 1 else ""}; {our_total} of your posts checked.'},
            "confidence": _confidence(t["confidence"], f'{t["competitor_posts"]} posts from {n_comp} competitors; {our_total} of your posts compared.'),
            "limitations": limitations,
            "suggested_format": fmt,
            "suggested_format_label": _format_label(fmt) if fmt else None,
            "next_step": f'Look at how competitors approached "{t["topic"]}", then outline an original angle for your audience.',
            "score": t["competitor_posts"] * n_comp * lift * rel_score,
        })
    return [_finish(r, ds, learned) for r in sorted(out, key=lambda r: -r["score"])[:MAX_PER_KIND * 2]]


# ---- 2. public audience questions ----

def question_recs(ds, learned):
    words = _relevance_words(ds.cfg)
    # Skip chit-chat ("what's her name?"): a useful question has a few words with meaning.
    qs = sorted((q for q in ds.questions if q.likes >= QUESTION_MIN_LIKES and _content_words(q.text) >= QUESTION_MIN_WORDS),
                key=lambda q: -q.likes)
    groups = []  # similar questions together: [main, others...]
    for q in qs:
        for g in groups:
            if fuzz.token_set_ratio(q.text.lower(), g[0].text.lower()) >= 75:
                g.append(q)
                break
        else:
            groups.append([q])
    checked_posts = {q.post_id for q in ds.questions}
    out = []
    for g in groups:
        main = g[0]
        post = ds.post_by_id[main.post_id]
        likes = sum(q.likes for q in g)
        rel_score, reason = _relevance(ds.cfg, " ".join(q.text for q in g) + " " + post.title, words)
        on_ours = ds.is_us(post)
        where = "your own video" if on_ours else f"{ds.by_id[post.competitor_id].name}'s video"
        observed = f'Asked on {where} "{post.title}"' + (f", plus {len(g) - 1} similar question(s)" if len(g) > 1 else "") + f"; {likes} like(s) in total."
        # One person asking is an anecdote, however many likes; several similar questions is a pattern.
        level = "medium" if len(g) >= 3 else "low"
        out.append({
            "key": f"audience_question:{main.comment_id}",
            "kind": "audience_question",
            "tone": "info",
            "title": f'Audience question: "{main.text[:140]}"',
            "topic": main.text[:80],
            "observed": observed,
            "detail": observed,
            "why_relevant": reason or "Asked by viewers of accounts you track, so likely relevant to a similar audience.",
            "evidence": {"posts": [ds.post_card(post)], "questions": [ds.question_card(q) for q in g[:5]],
                         "metrics": [{"label": "Likes on the question(s)", "value": likes},
                                     {"label": "Similar questions", "value": len(g)}]},
            "sample": {"questions": len(ds.questions), "videos_checked": len(checked_posts),
                       "text": f"{len(ds.questions)} questions found in the top comments of {len(checked_posts)} videos."},
            "confidence": _confidence(level, f"{len(g)} similar question(s) with {likes} like(s)."),
            "limitations": [
                "Only the top comments of a few most-viewed recent videos per account are read (to save API quota).",
                "Questions are detected by an English-only rule ('?' or a question word), so some are missed.",
                "Commenters are not a representative sample of the whole audience.",
            ],
            "suggested_format": ds.cfg["formats"][0] if ds.cfg["formats"] else ds.format(post),
            "suggested_format_label": _format_label(ds.cfg["formats"][0] if ds.cfg["formats"] else ds.format(post)),
            "next_step": "Answer this question in your own content, in more depth than a comment reply could.",
            "data_period": {"from": iso(min(q.published_at for q in g)), "to": iso(max(q.published_at for q in g)), "days": None},
            "score": (1 + likes) ** 0.5 * len(g) * rel_score,
        })
    return [_finish(r, ds, learned) for r in sorted(out, key=lambda r: -r["score"])[:MAX_PER_KIND]]


# ---- 3. competitor posts far above their own usual ----

def outlier_recs(ds, learned):
    words = _relevance_words(ds.cfg)
    out = []
    for p in ds.recent:
        r = ds.relative.get(p.id)
        if ds.is_us(p) or r is None or r < OUTLIER_RATIO:
            continue
        b = ds.baseline[p.competitor_id]
        acc = ds.by_id[p.competitor_id]
        rel_score, reason = _relevance(ds.cfg, p.title + " " + " ".join(getattr(p, "tags", None) or []), words)
        observed = (f'"{p.title}" by {acc.name} has {p.views:,} views, {r}× that account\'s usual '
                    f'{round(b["median_views"]):,} (median of {b["posts"]} posts).')
        level = "medium" if b["posts"] >= 15 else "low"
        out.append({
            "key": f"outlier:{p.id}",
            "kind": "outlier",
            "tone": "info",
            "title": f"{acc.name}: {r}× their usual views",
            "topic": p.title,
            "observed": observed,
            "detail": observed,
            "why_relevant": reason or f"{acc.name} is a competitor you track; posts far above their own baseline show what their audience responded to.",
            "evidence": {"posts": [ds.post_card(p)], "questions": [],
                         "metrics": [{"label": "Views", "value": p.views},
                                     {"label": "Account's usual views (median)", "value": round(b["median_views"])},
                                     {"label": "Relative performance", "value": f"{r}×", "definition": METRICS["relative_performance"]}]},
            "sample": {"baseline_posts": b["posts"], "text": f"Baseline from {b['posts']} of {acc.name}'s posts in the last {b['days']} days."},
            "confidence": _confidence(level, f"Baseline from {b['posts']} posts; this is one post."),
            "limitations": [
                "One post. Promotion, collaborations, trends or the algorithm may explain it; this data can't show the cause.",
                "Views keep growing after publishing, so very new and very old posts aren't perfectly comparable.",
            ],
            "suggested_format": ds.format(p),
            "suggested_format_label": _format_label(ds.format(p)),
            "next_step": "Study the topic, title, thumbnail and format. Decide whether an original take fits your audience. Don't copy it.",
            "score": r * rel_score,
        })
    return [_finish(r, ds, learned) for r in sorted(out, key=lambda r: -r["score"])[:MAX_PER_KIND]]


# ---- 4. formats that do well for competitors and that we rarely use ----

def format_recs(ds, learned, perf):
    window = [p for p in ds.posts if (ds.now - utc(p.published_at)).days <= PERF_DAYS]
    comp = defaultdict(list)
    ours = defaultdict(int)
    our_total = 0
    for p in window:
        f = ds.format(p)
        if not f:
            continue
        if ds.is_us(p):
            ours[f] += 1
            our_total += 1
        elif ds.relative.get(p.id) is not None:
            comp[f].append(p)
    out = []
    for f, ps in comp.items():
        accounts = {p.competitor_id for p in ps}
        if len(ps) < FORMAT_MIN_POSTS or len(accounts) < 2:
            continue
        med = median(ds.relative[p.id] for p in ps)
        share = ours[f] / our_total if our_total else 0
        if med < FORMAT_LIFT or share > 0.15:
            continue
        preferred = f in ds.cfg["formats"]
        defn = CONNECTORS["youtube"].formats.get(f) or CONNECTORS["rss"].formats.get(f, "")
        yours = (f"{ours[f]} of your {our_total} recent posts use this format." if our_total
                 else f"You have no posts in the last {PERF_DAYS} days to compare.")
        observed = (f"Competitors' {_format_label(f).lower()} posts get {round(med, 2)}× their usual views "
                    f"(median of {len(ps)} posts from {len(accounts)} accounts). {yours}")
        out.append({
            "key": f"format_test:{f}",
            "kind": "format_test",
            "tone": "info",
            "title": f"Worth testing: {_format_label(f)}",
            "topic": _format_label(f),
            "observed": observed,
            "detail": observed,
            "why_relevant": "You listed this as a preferred format." if preferred else
                            ("Not in your preferred formats. Shown because the data points to it; ignore it if it doesn't fit you."
                             if ds.cfg["formats"] else "Set preferred formats in Workspace to focus this list."),
            "evidence": {"posts": [ds.post_card(p) for p in sorted(ps, key=lambda p: -ds.relative[p.id])[:6]], "questions": [],
                         "metrics": [{"label": "Median relative performance", "value": f"{round(med, 2)}×", "definition": METRICS["relative_performance"]},
                                     {"label": "Format definition", "value": _format_label(f), "definition": defn}]},
            "sample": {"competitor_posts": len(ps), "competitor_accounts": len(accounts), "your_posts_checked": our_total,
                       "text": f"{len(ps)} competitor posts from {len(accounts)} accounts in the last {PERF_DAYS} days; {our_total} of yours."},
            "confidence": _confidence("medium" if len(ps) >= 15 and len(accounts) >= 3 else "low",
                                      f"{len(ps)} posts from {len(accounts)} accounts."),
            "limitations": [defn, "A format doing well for others doesn't mean it will for you. Test a few posts and compare with your own baseline."],
            "suggested_format": f,
            "suggested_format_label": _format_label(f),
            "next_step": f"Make 2–3 {_format_label(f).lower()} posts on topics you already know work, then compare them with your baseline.",
            "data_period": {"from": None, "to": iso(ds.now), "days": PERF_DAYS},
            "score": med * len(accounts) * (1.4 if preferred else 1.0),
        })
    # Length/Shorts findings from the Performance comparison.
    out += _from_performance(ds, perf, "format_test")
    return [_finish(r, ds, learned) for r in sorted(out, key=lambda r: -r["score"])[:MAX_PER_KIND]]


def _from_performance(ds, perf, kind):
    """Turn the Performance tab's comparison findings into fully explained recommendations."""
    us, market = perf.get("us"), perf.get("market")
    if not us or not market:
        return []
    out = []
    for s in perf["suggestions"]:
        if s.get("kind") != kind or s.get("metric") is None:
            continue
        level = "medium" if us["videos"] >= MIN_VIDEOS and market["videos"] >= MIN_VIDEOS and market["accounts"] >= 2 else "low"
        lim = ["Competitor numbers are an average of each competitor (each counts once, whatever its size)."]
        if s["metric"] == "best_time":
            lim = [f"Time slots use your workspace time zone ({ds.cfg['timezone']}).",
                   f"Your best slot is based on {us['best_time_sample']} video(s). A slot doing well may reflect the topics posted then, not the time itself."]
        if s["metric"] in ("median_views", "engagement_rate"):
            lim.append("Channels of very different sizes get very different views. Compare relative performance too.")
        if level == "low":
            lim.append(f"Fewer than {MIN_VIDEOS} videos on one side: a rough guide only.")
        title = s["title"] if kind != "publishing_pattern" else f"Worth investigating: {s['title'][0].lower()}{s['title'][1:]}"
        out.append({
            "key": f"{kind}:{s['metric']}",
            "kind": kind,
            "tone": s["tone"],
            "title": title,
            "topic": s["title"],
            "observed": s["detail"],
            "detail": s["detail"],
            "why_relevant": "Compared with the YouTube competitors you track in this workspace.",
            "evidence": {"posts": [], "questions": [], "metrics": [
                {"label": "You", "value": s["ours"]}, {"label": "Competitor average", "value": s["theirs"]},
                {"label": "Metric", "value": s["metric"], "definition": METRICS.get(s["metric"], "")}]},
            "sample": {"your_posts_checked": us["videos"], "competitor_posts": market["total_videos"],
                       "competitor_accounts": market["accounts"],
                       "text": f"{us['videos']} of your videos and {market['total_videos']} from {market['accounts']} competitors, last {PERF_DAYS} days."},
            "confidence": _confidence(level, f"{us['videos']} vs {market['total_videos']} videos."),
            "limitations": lim,
            "suggested_format": None,
            "suggested_format_label": None,
            "next_step": "Try it on a few posts and compare them with your own baseline before changing your plan.",
            "data_period": {"from": None, "to": iso(ds.now), "days": PERF_DAYS},
            "score": 1.0,
        })
    return out


def build(ds, perf, learned=None):
    """All recommendations, best first, each with full evidence."""
    learned = learned or {}
    recs = (topic_recs(ds, learned) + question_recs(ds, learned) + outlier_recs(ds, learned)
            + format_recs(ds, learned, perf)
            + [_finish(r, ds, learned) for r in _from_performance(ds, perf, "publishing_pattern")]
            + [_finish(r, ds, learned) for r in _from_performance(ds, perf, "benchmark")])
    # Raw scores mean different things per kind (posts × accounts, likes, ×-baseline), so scale
    # each kind to 0–1 first; then goals, confidence and past outcomes decide the mixed order.
    top = {}
    for r in recs:
        top[r["kind"]] = max(top.get(r["kind"], 0), r["score"])
    for r in recs:
        r["score"] = round((r["score"] / top[r["kind"]] if top[r["kind"]] else 0) * r.pop("weight"), 3)
    recs.sort(key=lambda r: -r["score"])
    return recs


def readiness(ds, perf):
    """What's missing before recommendations can be trusted (shown instead of generic advice)."""
    needs = []
    if not ds.cfg["configured"]:
        needs.append("Set up your workspace (type, niche, topics, goals) so recommendations can be ranked for you.")
    if not ds.us_ids:
        needs.append("Add at least one of your own accounts (tick 'Ours') in Accounts.")
    if len([a for a in ds.accounts if not a.is_us]) < 2:
        needs.append("Track at least 2 competitor accounts for comparisons to mean anything.")
    if not ds.posts:
        needs.append("Click Refresh to collect posts.")
    if ds.posts and not ds.questions and any(a.platform == "youtube" for a in ds.accounts):
        needs.append("No audience questions collected yet. They're read from YouTube comments on Refresh.")
    return needs