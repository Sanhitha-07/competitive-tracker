"""Opportunity lifecycle: recommendation -> brief -> MediaOps draft -> scheduled -> published -> evaluated.

The original recommendation is frozen into the Opportunity when the user first acts on it,
so the link between "what we suggested", "what was made" and "what happened" survives later refreshes.

Outcome = our published post's views compared with our own usual views (baseline), measured
EVAL_AFTER_DAYS after publishing. It says whether the post did better than usual, never why.
"""
from datetime import datetime, timedelta, timezone

from sqlmodel import select

import workspace
from dataset import iso, utc
from models import MetricSnapshot, Opportunity, Post

EVAL_AFTER_DAYS = 7
WITHIN = 0.2  # within ±20% of baseline counts as "about usual"

TRANSITIONS = {
    "saved": {"brief", "in_mediaops", "scheduled", "dismissed"},
    "brief": {"in_mediaops", "scheduled", "published", "dismissed", "saved"},
    "in_mediaops": {"scheduled", "published", "dismissed"},
    "scheduled": {"in_mediaops", "published", "dismissed"},
    "published": {"evaluated"},
    "evaluated": set(),
    "dismissed": {"saved"},
}


def now_utc():
    return datetime.now(timezone.utc)


def record(opp, status, note=None):
    if status != opp.status and status not in TRANSITIONS.get(opp.status, set()):
        raise ValueError(f'Can\'t move from "{opp.status}" to "{status}".')
    opp.status = status
    opp.updated_at = now_utc()
    opp.history = [*(opp.history or []), {"status": status, "at": iso(opp.updated_at), "note": note}]


def make_brief(rec, cfg, baseline=None):
    """An original-content brief built from the evidence. Template-based: no AI, nothing invented."""
    posts = rec["evidence"].get("posts", [])
    questions = rec["evidence"].get("questions", [])
    audience = cfg["audience"] or "your audience"
    fmt = rec.get("suggested_format_label") or "a format that suits you"
    goals = [workspace.GOALS[g][0] for g in cfg["goals"]]
    measure = "views after 7 days"
    if "engagement" in cfg["goals"] or "community" in cfg["goals"]:
        measure = "likes + comments per view after 7 days"
    base_txt = (f"Compare with your usual {baseline['median_views']:,.0f} views (median of {baseline['posts']} posts)."
                if baseline else "Your baseline appears here once you have 5+ posts older than 48 hours.")
    return {
        "working_title": f"[Your own title about: {rec.get('topic') or rec['title']}]",
        "objective": "; ".join(goals) if goals else "Set goals in Workspace to tailor this.",
        "audience": audience,
        "angle": (f"Make this for {audience}. Look at what the references below do NOT cover, "
                  f"and lead with your own experience, data or point of view."),
        "observation": rec["observed"],
        "why": rec["why_relevant"],
        "questions_to_answer": [q["text"] for q in questions[:5]],
        "format": fmt,
        "references": [{"title": p["title"], "link": p["link"], "account": p["account"]} for p in posts[:5]],
        "originality_note": "References are for research only. Don't reuse their titles, scripts, thumbnails or footage.",
        "success_measure": f"{measure}. {base_txt}",
        "evidence_strength": rec["confidence"]["level"],
        "limitations": rec["limitations"],
    }


def brief_text(opp):
    b = opp.brief or {}
    lines = [
        f"Working title: {b.get('working_title', opp.title)}",
        f"Objective: {b.get('objective', '')}",
        f"Audience: {b.get('audience', '')}",
        f"Format: {b.get('format', '')}",
        f"Angle: {b.get('angle', '')}",
        f"What we saw: {b.get('observation', '')}",
        f"Why it matters to us: {b.get('why', '')}",
    ]
    if b.get("questions_to_answer"):
        lines.append("Questions to answer:")
        lines += [f"- {q}" for q in b["questions_to_answer"]]
    if b.get("references"):
        lines.append("References (research only, do not copy):")
        lines += [f"- {r['account']}: {r['title']} {r['link']}" for r in b["references"]]
    lines.append(f"How we'll measure it: {b.get('success_measure', '')}")
    lines.append(f"Evidence strength: {b.get('evidence_strength', '')}")
    lines.append(f"Source: Competitive Tracker opportunity #{opp.id}")
    return "\n".join(lines)


def normalize_link(link):
    """Same video, different link styles -> one canonical link, so we can match our published post."""
    link = (link or "").strip()
    try:
        import youtube
        kind, value = youtube._lookups(link)[0]
        if kind == "video":
            return f"https://www.youtube.com/watch?v={value}"
    except Exception:
        pass
    return link


def match_published(session, opp, our_account_ids):
    """Find our post for the published link once our account has been refreshed."""
    if opp.published_post_id or not opp.published_link or not our_account_ids:
        return None
    link = normalize_link(opp.published_link)
    post = session.exec(select(Post).where(Post.competitor_id.in_(our_account_ids), Post.link == link)).first()
    if post:
        opp.published_post_id = post.id
    return post


def views_at(session, post, days):
    """Views about `days` after publishing, from snapshots; falls back to the latest number."""
    target = utc(post.published_at) + timedelta(days=days)
    snaps = session.exec(select(MetricSnapshot).where(MetricSnapshot.post_id == post.id)).all()
    after = sorted((s for s in snaps if utc(s.captured_at) >= target), key=lambda s: utc(s.captured_at))
    if after:
        return after[0].views, utc(after[0].captured_at)
    return post.views, utc(post.metrics_updated_at) if post.metrics_updated_at else None


def evaluate(session, opp, ds):
    """Compare our published post with our own baseline once it's EVAL_AFTER_DAYS old."""
    post = session.get(Post, opp.published_post_id) if opp.published_post_id else None
    if not post:
        return None
    age = (ds.now - utc(post.published_at)).total_seconds() / 86400
    base = ds.baseline.get(post.competitor_id)
    if age < EVAL_AFTER_DAYS:
        return {"state": "measuring", "age_days": round(age, 1),
                "note": f"Measured {EVAL_AFTER_DAYS} days after publishing ({round(EVAL_AFTER_DAYS - age, 1)} days to go)."}
    if post.views is None or not base:
        return {"state": "not_measurable", "note": "This platform has no view counts, or you don't have 5+ older posts to form a baseline."}
    views, measured_at = views_at(session, post, EVAL_AFTER_DAYS)
    ratio = round(views / base["median_views"], 2) if base["median_views"] else None
    verdict = "about_usual"
    if ratio is not None and ratio >= 1 + WITHIN:
        verdict = "above_usual"
    elif ratio is not None and ratio <= 1 - WITHIN:
        verdict = "below_usual"
    late = measured_at and (measured_at - utc(post.published_at)).days > EVAL_AFTER_DAYS + 2
    return {
        "state": "evaluated", "views": views, "measured_at": iso(measured_at),
        "baseline_views": round(base["median_views"]), "baseline_posts": base["posts"],
        "ratio": ratio, "verdict": verdict, "post_title": post.title, "post_link": post.link,
        "note": ("Compared with your usual views. Many things affect a post's results, so this doesn't show "
                 "the recommendation caused it.") + (" Measured later than 7 days (no earlier snapshot), so views may be higher than a 7-day number." if late else ""),
    }


def learned_stats(session, org_id):
    """Per recommendation kind: how many evaluated, how many beat the baseline."""
    stats = {}
    for o in session.exec(select(Opportunity).where(Opportunity.org_id == org_id)).all():
        s = stats.setdefault(o.kind, {"accepted": 0, "implemented": 0, "evaluated": 0, "above": 0, "dismissed": 0})
        if o.status == "dismissed":
            s["dismissed"] += 1
            continue
        s["accepted"] += 1
        if o.status in ("published", "evaluated"):
            s["implemented"] += 1
        if o.outcome and o.outcome.get("state") == "evaluated":
            s["evaluated"] += 1
            s["above"] += o.outcome.get("verdict") == "above_usual"
    return stats


def ics(opp):
    """A calendar file the user can import into Google/Outlook or MediaOps Schedules."""
    start = utc(opp.planned_for)
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    desc = brief_text(opp).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    summary = opp.title.replace(",", "\\,").replace(";", "\\;")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MediaOps//Competitive Tracker//EN",
        "BEGIN:VEVENT", f"UID:ct-opportunity-{opp.id}@mediaops", f"DTSTAMP:{stamp}",
        f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}",
        f"DTEND:{(start + timedelta(hours=1)).strftime('%Y%m%dT%H%M%SZ')}",
        f"SUMMARY:Content: {summary}", f"DESCRIPTION:{desc}", "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def _fold(line, width=73):
    """Calendar files must wrap lines longer than 75 characters (continuation lines start with a space)."""
    parts = [line[i:i + width] for i in range(0, len(line), width)] or [""]
    return "\r\n ".join(parts)
