"""The Dashboard: everything computed elsewhere, condensed into plain language and chart data.

Nothing new is inferred here. Each briefing line restates a number from the analysis
(posts, relative performance, engagement, topics, trends) in words a non-analyst can read,
with a tone (good / bad / warn / info) and the tab where the evidence is.
"""
from collections import defaultdict
from datetime import timedelta
from statistics import median

from connectors import interactions
from dataset import iso, utc

PLATFORM_LABEL = {"youtube": "YouTube", "instagram": "Instagram", "facebook": "Facebook", "rss": "Website"}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SLOTS = [("Night", 0, 5), ("Morning", 5, 12), ("Afternoon", 12, 17), ("Evening", 17, 22), ("Night", 22, 24)]
SLOT_ORDER = ["Morning", "Afternoon", "Evening", "Night"]


def _slot(hour):
    return next(name for name, lo, hi in SLOTS if lo <= hour < hi)


def _pct(a, b):
    return round(a / b * 100) if b else 0


def period_days(cfg):
    """Dashboard period: a week for fast-moving news and sport, otherwise a month."""
    return 7 if cfg["time_sensitive"] else 30


def _names(ds):
    """Accounts grouped by name, so one competitor's YouTube + Instagram + Facebook count as one."""
    groups = {}
    for a in ds.accounts:
        g = groups.setdefault(a.name, {"name": a.name, "is_us": a.is_us, "ids": set(), "platforms": set(),
                                       "thumbnail": None, "audience": 0})
        g["ids"].add(a.id)
        g["platforms"].add(a.platform)
        g["is_us"] = g["is_us"] or a.is_us
        g["thumbnail"] = g["thumbnail"] or a.thumbnail
        g["audience"] += a.subscribers or 0
    return sorted(groups.values(), key=lambda g: (not g["is_us"], g["name"]))


def share_of_voice(ds, posts, groups):
    total_posts = len(posts)
    total_inter = sum(interactions(p) or 0 for p in posts)
    rows = []
    for g in groups:
        mine = [p for p in posts if p.competitor_id in g["ids"]]
        inter = sum(interactions(p) or 0 for p in mine)
        rows.append({"name": g["name"], "is_us": g["is_us"], "posts": len(mine), "interactions": inter,
                     "audience": g["audience"] or None, "platforms": sorted(g["platforms"]),
                     "thumbnail": g["thumbnail"],
                     "share_posts": _pct(len(mine), total_posts), "share_interactions": _pct(inter, total_inter)})
    rows.sort(key=lambda r: (-r["posts"], r["name"]))
    return {"rows": rows, "total_posts": total_posts, "total_interactions": total_inter,
            "definition": "Share of voice = an account's share of all posts (and of all public likes, comments and shares) "
                          "published by the accounts you track in the period. Accounts with the same name on several platforms are combined."}


def activity(ds, groups, days):
    """Posts per account per bucket (day for a 7-day period, week otherwise)."""
    daily = days <= 7
    start = ds.now - timedelta(days=days if daily else 7 * 8)
    if daily:
        buckets = [(start + timedelta(days=i + 1)).date().isoformat() for i in range(days)]
    else:
        monday = (ds.now - timedelta(days=ds.now.weekday())).date()
        buckets = [(monday - timedelta(weeks=7 - i)).isoformat() for i in range(8)]
    series = []
    for g in groups:
        counts = dict.fromkeys(buckets, 0)
        for p in ds.posts:
            if p.competitor_id not in g["ids"] or utc(p.published_at) < start:
                continue
            d = utc(p.published_at).astimezone(ds.tz).date()
            key = d.isoformat() if daily else (d - timedelta(days=d.weekday())).isoformat()
            if key in counts:
                counts[key] += 1
        series.append({"name": g["name"], "is_us": g["is_us"], "values": [counts[b] for b in buckets]})
    return {"unit": "day" if daily else "week", "buckets": buckets, "series": series}


def platform_mix(ds, posts):
    rows = defaultdict(lambda: {"ours": 0, "theirs": 0})
    for p in posts:
        rows[p.platform]["ours" if ds.is_us(p) else "theirs"] += 1
    return [{"platform": k, "label": PLATFORM_LABEL.get(k, k), **v} for k, v in sorted(rows.items())]


def format_mix(ds, posts):
    ours, theirs = defaultdict(int), defaultdict(int)
    for p in posts:
        f = ds.format(p) or "other"
        (ours if ds.is_us(p) else theirs)[f] += 1
    n_o, n_t = sum(ours.values()), sum(theirs.values())
    fmts = sorted(set(ours) | set(theirs), key=lambda f: -(ours[f] + theirs[f]))
    return {"rows": [{"format": f, "ours": ours[f], "theirs": theirs[f], "ours_pct": _pct(ours[f], n_o),
                      "theirs_pct": _pct(theirs[f], n_t)} for f in fmts],
            "our_total": n_o, "their_total": n_t}


def best_times(ds, posts):
    """Competitors' posts by weekday × time of day: how many, and their median relative performance."""
    cells = defaultdict(list)
    counts = defaultdict(int)
    for p in posts:
        if ds.is_us(p):
            continue
        local = utc(p.published_at).astimezone(ds.tz)
        key = (local.weekday(), _slot(local.hour))
        counts[key] += 1
        if ds.relative.get(p.id) is not None:
            cells[key].append(ds.relative[p.id])
    grid = []
    for d in range(7):
        for sl in SLOT_ORDER:
            vals = cells.get((d, sl), [])
            grid.append({"day": DAYS[d], "slot": sl, "posts": counts.get((d, sl), 0),
                         "median_relative": round(median(vals), 2) if len(vals) >= 2 else None, "sample": len(vals)})
    best = sorted((c for c in grid if c["median_relative"] is not None and c["sample"] >= 3),
                  key=lambda c: -c["median_relative"])[:3]
    return {"grid": grid, "days": DAYS, "slots": SLOT_ORDER, "best": best, "timezone": str(ds.tz),
            "definition": "Each cell: competitors' posts published then, and their median performance vs each account's usual (1.0× = usual). Cells with fewer than 2 measured posts are blank."}


def top_posts(ds, posts, n=6):
    measured = [p for p in posts if ds.relative.get(p.id) is not None]
    theirs = sorted((p for p in measured if not ds.is_us(p)), key=lambda p: -ds.relative[p.id])[:n]
    ours = sorted((p for p in measured if ds.is_us(p)), key=lambda p: -ds.relative[p.id])[:3]
    return {"competitors": [ds.post_card(p) for p in theirs], "ours": [ds.post_card(p) for p in ours]}


def audience(ds, snapshots, days):
    """Audience size now and its change over the period, per account (from saved snapshots)."""
    since = ds.now - timedelta(days=days)
    out = []
    for a in ds.accounts:
        snaps = sorted((s for s in snapshots.get(a.id, []) if s.subscribers is not None and utc(s.captured_at) >= since),
                       key=lambda s: utc(s.captured_at))
        change = snaps[-1].subscribers - snaps[0].subscribers if len(snaps) >= 2 else None
        pct = round(change / snaps[0].subscribers * 100, 1) if change is not None and snaps[0].subscribers else None
        out.append({"id": a.id, "name": a.name, "platform": a.platform, "is_us": a.is_us, "audience": a.subscribers,
                    "change": change, "change_pct": pct, "since": iso(snaps[0].captured_at) if snaps else None,
                    "points": [{"at": iso(s.captured_at), "value": s.subscribers} for s in snaps][-30:]})
    return out


def _fmt(n):
    if n is None:
        return "–"
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= div:
            return f"{n / div:.1f}".rstrip("0").rstrip(".") + suf
    if isinstance(n, float) and abs(n) < 100:
        return f"{n:.2f}".rstrip("0").rstrip(".")
    return f"{n:,.0f}" if isinstance(n, (int, float)) else str(n)


def briefing(ds, perf, recs, trend_items, sov, days, topic_rows):
    """Plain-language "what's happening" lines, most important first."""
    lines = []

    def add(tone, title, text, tab, weight):
        lines.append({"tone": tone, "title": title, "text": text, "tab": tab, "weight": weight})

    ours = next((r for r in sov["rows"] if r["is_us"]), None)
    comps = [r for r in sov["rows"] if not r["is_us"]]
    if ours and comps:
        avg = sum(r["posts"] for r in comps) / len(comps)
        leader = max(comps, key=lambda r: r["posts"])
        if ours["posts"] < 0.7 * avg:
            add("bad", "You're posting less than competitors",
                f"You published {ours['posts']} posts in the last {days} days; competitors averaged {avg:.0f} "
                f"({leader['name']} posted the most: {leader['posts']}). Posting regularly keeps you visible.", "performance", 8)
        elif ours["posts"] > 1.3 * avg:
            add("good", "You're the most active",
                f"You published {ours['posts']} posts in the last {days} days vs a competitor average of {avg:.0f}.", "performance", 4)
        else:
            add("info", "Your posting pace matches the market",
                f"{ours['posts']} posts in the last {days} days; competitors averaged {avg:.0f}.", "performance", 3)
        if sov["total_interactions"]:
            share = ours["share_interactions"]
            fair = round(100 / len(sov["rows"]))
            tone = "good" if share >= fair else "warn"
            add(tone, f"You get {share}% of the audience's attention",
                f"Of all public likes, comments and shares on the {len(sov['rows'])} accounts you track, {share}% went to you "
                f"({ours['share_posts']}% of the posts). An even split would be about {fair}%.", "dashboard", 6 if tone == "warn" else 4)

    for platform, block in (perf.get("platforms") or {}).items():
        us, market = block.get("us"), block.get("market")
        if not us or not market:
            continue
        label = PLATFORM_LABEL.get(platform, platform)
        if platform == "youtube":
            a, b, what = us["median_views"], market["median_views"], "views on a typical video"
        else:
            a, b, what = us.get("engagement_rate"), market.get("engagement_rate"), "engagement per follower"
        if a is None or not b:
            continue
        diff = round((a - b) / b * 100)
        unit = "%" if platform != "youtube" else ""
        if diff <= -20:
            add("bad", f"{label}: behind on {what}",
                f"You: {_fmt(a)}{unit} vs competitors' {_fmt(b)}{unit} ({diff}%). See which of their posts did best and why.", "performance", 7)
        elif diff >= 20:
            add("good", f"{label}: ahead on {what}",
                f"You: {_fmt(a)}{unit} vs competitors' {_fmt(b)}{unit} (+{diff}%). Keep doing what works.", "performance", 5)

    mine = [p for p in ds.posts if ds.is_us(p) and utc(p.published_at) >= ds.now - timedelta(days=days)
            and ds.relative.get(p.id) is not None]
    if mine:
        best = max(mine, key=lambda p: ds.relative[p.id])
        if ds.relative[best.id] >= 1.5:
            add("good", "Your standout post",
                f'"{best.title}" did {ds.relative[best.id]}× your usual on {PLATFORM_LABEL.get(best.platform, best.platform)}. '
                "Make more like it: same topic, a new angle.", "explorer", 6)

    outliers = [r for r in recs if r["kind"] == "outlier"]
    if outliers:
        o = outliers[0]
        add("info", "A competitor post took off", o["observed"] + " Look at its topic, hook and format; don't copy it.", "suggestions", 5)

    gaps = [t for t in topic_rows if t["status"] == "not_covered_by_you" and t["competitor_posts"] >= 3 and len(t["competitors"]) >= 2]
    if gaps:
        shown = []
        for t in gaps:  # "diwali sweets" makes "diwali" and "sweets" redundant
            if not any(set(t["topic"].split()) <= set(x["topic"].split()) or set(x["topic"].split()) <= set(t["topic"].split()) for x in shown):
                shown.append(t)
        names = ", ".join(f'"{t["topic"]}"' for t in shown[:3])
        add("warn", "Topics your competitors cover and you don't",
            f"{names}: each covered by 2+ competitors in this period, none by you.", "gaps", 7)

    # Only trends that are fine to join are presented as opportunities; "with care" ones only to newsrooms.
    usable = [t for t in trend_items if t["advice"]["action"] == "go"
              or (t["advice"]["action"] == "care" and ds.cfg["brand_safety"] == "newsroom")]
    early = [t for t in usable if not t["coverage"]["competitors"] and not t["coverage"]["yours"]]
    late = [t for t in usable if t["coverage"]["competitors"] and not t["coverage"]["yours"]]

    def care(t):
        return f' {t["advice"]["label"]}: {t["advice"]["advice"]}' if t["advice"]["action"] == "care" else ""

    if late:
        t = late[0]
        add("warn", "Competitors are already on a trend",
            f'"{t["title"]}" ({t["signal"]}). {t["coverage"]["text"]}{care(t)}', "trends", 8)
    if early:
        t = early[0]
        add("good", "A chance to be first",
            f'"{t["title"]}" is trending ({t["signal"]}) and fits your workspace. No one you track has posted about it yet.{care(t)}', "trends", 7)
    avoid = [t for t in trend_items if t["advice"]["action"] == "avoid"]
    if avoid:
        add("info", f"{len(avoid)} sensitive trend{'s' if len(avoid) != 1 else ''} to stay away from",
            "Related to your field but involving " + ", ".join(sorted({lbl.lower() for t in avoid for lbl in t["sensitivity"]["labels"]})[:3])
            + f". Under your brand-safety setting ({ds.cfg['brand_safety']}) we won't suggest them.", "trends", 2)

    fresh = ds.freshness()
    if fresh["hours_ago"] is None:
        add("warn", "No data yet", "Click Refresh to collect posts from the accounts you track.", "accounts", 10)
    elif fresh["hours_ago"] > 48:
        add("warn", "Data is getting old", f"Last refresh was {round(fresh['hours_ago'] / 24)} days ago. Click Refresh for current numbers.", "dashboard", 9)

    lines.sort(key=lambda x: -x["weight"])
    good = sum(1 for x in lines if x["tone"] == "good")
    bad = sum(1 for x in lines if x["tone"] in ("bad", "warn"))
    if not lines:
        headline = "Add accounts and click Refresh to see what's happening."
    elif good and not bad:
        headline = "You're doing well against the competitors you track."
    elif bad > good:
        headline = f"{bad} thing{'s' if bad != 1 else ''} need{'s' if bad == 1 else ''} attention, starting with the first item below."
    else:
        headline = f"A mixed picture: {good} strength{'s' if good != 1 else ''} and {bad} area{'s' if bad != 1 else ''} to work on."
    return {"headline": headline, "items": [{k: v for k, v in x.items() if k != "weight"} for x in lines[:9]]}


def kpis(ds, sov, perf, trend_items, recs, days, topic_rows):
    ours = next((r for r in sov["rows"] if r["is_us"]), None)
    comps = [r for r in sov["rows"] if not r["is_us"]]
    avg = round(sum(r["posts"] for r in comps) / len(comps), 1) if comps else None
    measured = [ds.relative[p.id] for p in ds.posts if ds.is_us(p) and ds.relative.get(p.id) is not None
                and utc(p.published_at) >= ds.now - timedelta(days=days)]
    our_rel = round(median(measured), 2) if measured else None
    return [
        {"id": "posts", "label": "Your posts", "value": ours["posts"] if ours else None,
         "hint": f"competitor avg {avg}" if avg is not None else "add competitors", "tone":
         ("good" if ours and avg is not None and ours["posts"] >= avg else "bad" if ours and avg else "")},
        {"id": "sov", "label": "Share of attention", "value": f"{ours['share_interactions']}%" if ours and sov["total_interactions"] else None,
         "hint": "of likes, comments & shares", "tone": ""},
        {"id": "relative", "label": "Your posts vs your usual", "value": f"{our_rel}×" if our_rel else None,
         "hint": "median; 1.0× = your normal", "tone": "good" if our_rel and our_rel >= 1.1 else "bad" if our_rel and our_rel < 0.9 else ""},
        {"id": "gaps", "label": "Topics to review", "value": sum(1 for t in topic_rows if t["status"] in ("not_covered_by_you", "covered_less") and t["competitor_posts"] >= 2),
         "hint": "competitors cover more than you", "tone": "warn"},
        {"id": "trends", "label": "Relevant trends", "value": sum(1 for t in trend_items if t["advice"]["action"] != "avoid"),
         "hint": f"{sum(1 for t in trend_items if t['rising'])} rising · {sum(1 for t in trend_items if t['advice']['action'] == 'avoid')} to avoid", "tone": ""},
        {"id": "actions", "label": "Suggested actions", "value": sum(1 for r in recs if r["actionable"]),
         "hint": "backed by your data", "tone": ""},
    ]


def build(ds, perf, recs, trend_items, snapshots):
    days = period_days(ds.cfg)
    since = ds.now - timedelta(days=days)
    posts = [p for p in ds.posts if utc(p.published_at) >= since]
    groups = _names(ds)
    sov = share_of_voice(ds, posts, groups)
    topic_rows, _ = ds.topics()
    priorities = [{"key": r["key"], "kind": r["kind"], "kind_label": r["kind_label"], "title": r["title"],
                   "next_step": r["next_step"], "confidence": r["confidence"]["level"], "tone": r["tone"],
                   "platform": r.get("platform")}
                  for r in recs if r["actionable"]][:5]
    return {
        "period": {"days": days, "from": iso(since), "to": iso(ds.now)},
        "freshness": ds.freshness(),
        "briefing": briefing(ds, perf, recs, trend_items, sov, days, topic_rows),
        "kpis": kpis(ds, sov, perf, trend_items, recs, days, topic_rows),
        "share_of_voice": sov,
        "activity": activity(ds, groups, days),
        "platform_mix": platform_mix(ds, posts),
        "format_mix": format_mix(ds, posts),
        "best_times": best_times(ds, posts),
        "top_posts": top_posts(ds, posts),
        "audience": audience(ds, snapshots, days),
        "engagement": [
            {"platform": pid, "label": PLATFORM_LABEL.get(pid, pid), "metric": block["metric"],
             "rows": [{"name": r["name"], "is_us": r["is_us"],
                       "value": (r["stats"] or {}).get("engagement_rate"),
                       "typical": (r["stats"] or {}).get("median_views" if pid == "youtube" else "median_interactions")}
                      for r in block["accounts"] if r["stats"]],
             "definition": ("(likes + comments) ÷ views × 100" if pid == "youtube" else "interactions ÷ followers × 100, per post")}
            for pid, block in (perf.get("platforms") or {}).items()
        ],
        "trends": trend_items[:6],
        "priorities": priorities,
        "accounts": {"ours": sum(1 for a in ds.accounts if a.is_us), "competitors": len({a.name for a in ds.accounts if not a.is_us}),
                     "platforms": sorted({a.platform for a in ds.accounts})},
    }


def ai_input(dash, cfg):
    """A compact, number-only summary for the optional AI briefing (no post bodies, no personal data)."""
    return {
        "workspace": {k: cfg[k] for k in ("creator_type", "industry_label", "niche", "audience", "goals", "region_label", "brand_safety")},
        "period_days": dash["period"]["days"],
        "kpis": [{k: x[k] for k in ("label", "value", "hint")} for x in dash["kpis"]],
        "briefing": [{k: x[k] for k in ("tone", "title", "text")} for x in dash["briefing"]["items"]],
        "share_of_voice": [{k: r[k] for k in ("name", "is_us", "posts", "share_posts", "share_interactions")} for r in dash["share_of_voice"]["rows"]],
        "format_mix": dash["format_mix"]["rows"][:8],
        "best_times": dash["best_times"]["best"],
        "priorities": [{k: p[k] for k in ("kind_label", "title", "next_step", "confidence")} for p in dash["priorities"]],
        "trends": [{"title": t["title"], "signal": t["signal"], "sensitivity": t["sensitivity"]["level"],
                    "advice": t["advice"]["label"], "coverage": t["coverage"]["text"]} for t in dash["trends"]],
    }
