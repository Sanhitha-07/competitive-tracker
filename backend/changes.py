"""Competitor Change Detector: notable changes in competitors' public data.

Checked whenever the activity feed is opened, using the posts and numbers saved at each Refresh.
It is not real-time monitoring: a change shows up only after a Refresh has collected it.

Each event has a stable key, so the same change is stored once and never listed again
(a frequency or audience change can come back only in a later 4-week block).

Kinds:
  frequency  publishing rate in the last 2 weeks vs the 6 weeks before (needs complete history)
  format     a format the account didn't use in the previous 6 weeks
  standout   a recent post far above the account's own usual views
  topic      a topic in 2+ recent posts that the account didn't post about before
  audience   public subscriber count changed 5%+ over the last ~30 days (from saved snapshots)
"""
from datetime import datetime, timedelta, timezone

import topics as topic_map
from dataset import iso, utc
from dna import _main_topics

RECENT_DAYS = 14
PRIOR_DAYS = 42
FREQ_CHANGE = 0.5        # 50%+ change in posts per week
FREQ_MIN_POSTS = 6
STANDOUT_RATIO = 2.5
TOPIC_PRIOR_MIN = 8       # the account needs this many earlier posts before "new topic" means anything
AUDIENCE_CHANGE = 0.05
AUDIENCE_MIN_ABS = 100
BUCKET_DAYS = 28
EPOCH = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _bucket(now):
    return (now - EPOCH).days // BUCKET_DAYS


def _event(key, kind, account, title, what, why, action, previous=None, current=None, period=None, evidence=()):
    return {"key": key, "kind": kind, "account_id": account.id, "title": title,
            "detail": {"account": account.name, "platform": account.platform, "what": what, "why": why,
                       "previous": previous, "current": current, "period": period,
                       "evidence": list(evidence), "action": action}}


def detect(ds, audience_snaps=None):
    audience_snaps = audience_snaps or {}
    now = ds.now
    recent_start = now - timedelta(days=RECENT_DAYS)
    prior_start = recent_start - timedelta(days=PRIOR_DAYS)
    bucket = _bucket(now)
    rules = getattr(ds.org, "topic_rules", None)
    events = []

    for a in ds.accounts:
        if a.is_us:
            continue
        mine = [p for p in ds.posts if p.competitor_id == a.id]
        if not mine:
            continue
        oldest = min(utc(p.published_at) for p in mine)
        recent = [p for p in mine if utc(p.published_at) >= recent_start]
        prior = [p for p in mine if prior_start <= utc(p.published_at) < recent_start]
        # We only know an account's full prior period if we have posts from before it started;
        # otherwise a channel list that returns only recent videos would look like a sudden increase.
        complete = oldest <= prior_start

        if complete and len(recent) + len(prior) >= FREQ_MIN_POSTS:
            r_rate, p_rate = len(recent) / RECENT_DAYS * 7, len(prior) / PRIOR_DAYS * 7
            if p_rate and abs(r_rate - p_rate) / p_rate >= FREQ_CHANGE:
                up = r_rate > p_rate
                events.append(_event(
                    f"frequency:{a.id}:{'up' if up else 'down'}:{bucket}", "frequency", a,
                    f"{a.name} is posting {'more' if up else 'less'} often",
                    f"{round(r_rate, 1)} posts a week in the last {RECENT_DAYS} days vs {round(p_rate, 1)} in the {PRIOR_DAYS} days before.",
                    "A change in rhythm can mean a new series, a campaign or a slowdown. Check what the recent posts are about.",
                    {"label": "See their recent posts", "type": "explorer", "account_id": a.id},
                    previous=f"{round(p_rate, 1)} / week", current=f"{round(r_rate, 1)} / week",
                    period={"from": iso(prior_start), "to": iso(now)},
                    evidence=[ds.post_card(p) for p in sorted(recent, key=lambda p: p.published_at, reverse=True)[:4]]))

        if complete and len(prior) >= 5:
            before = {ds.format(p) for p in mine if utc(p.published_at) < recent_start}
            for fmt in sorted({ds.format(p) for p in recent} - before - {None}):
                ps = [p for p in recent if ds.format(p) == fmt]
                events.append(_event(
                    f"format:{a.id}:{fmt}", "format", a, f"{a.name} published a new format: {fmt}",
                    f"{len(ps)} {fmt} post{'s' if len(ps) != 1 else ''} in the last {RECENT_DAYS} days; none in the {len(prior)} posts before.",
                    "Trying a new format can be a test worth watching. Its results show in the account's next refreshes.",
                    {"label": "Create a brief from it", "type": "brief_post", "post_id": ps[0].id},
                    previous="not used", current=f"{len(ps)} post(s)", period={"from": iso(recent_start), "to": iso(now)},
                    evidence=[ds.post_card(p) for p in ps[:4]]))

        for p in recent:
            r = ds.relative.get(p.id)
            if r is not None and r >= STANDOUT_RATIO:
                b = ds.baseline[a.id]
                events.append(_event(
                    f"standout:{p.id}", "standout", a, f"{a.name}: a post at {r}× their usual views",
                    f'"{p.title}" has {p.views:,} views vs the account\'s usual {round(b["median_views"]):,} (median of {b["posts"]} posts).',
                    "Shows what this account's audience responded to recently. One post can't show the cause.",
                    {"label": "Create a brief from it", "type": "brief_post", "post_id": p.id},
                    previous=f"usual {round(b['median_views']):,} views", current=f"{p.views:,} views",
                    period={"from": iso(p.published_at), "to": iso(getattr(p, "metrics_updated_at", None) or now)},
                    evidence=[ds.post_card(p)]))

        earlier = [p for p in mine if utc(p.published_at) < recent_start]
        if len(earlier) >= TOPIC_PRIOR_MIN and len(recent) >= 2:
            known = {t for p in earlier for t in topic_map.post_terms(p, topic_map._account_words([a]))}
            fresh = [t for t in _main_topics(a, recent, rules, 10) if t["topic"] not in known][:2]
            for t in fresh:
                ps = [p for p in recent if topic_map._matches(t["topic"], p)]
                events.append(_event(
                    f"topic:{a.id}:{t['topic']}", "topic", a, f'{a.name} started posting about "{t["topic"]}"',
                    f'{t["posts"]} posts on it in the last {RECENT_DAYS} days; none in their {len(earlier)} earlier posts we have.',
                    "A new recurring topic at a competitor may be an emerging trend in your niche.",
                    {"label": "Create a brief on this topic", "type": "brief_topic", "topic": t["topic"]},
                    previous="0 posts", current=f"{t['posts']} posts", period={"from": iso(recent_start), "to": iso(now)},
                    evidence=[ds.post_card(p) for p in ps[:4]]))

        snaps = sorted(audience_snaps.get(a.id, []), key=lambda s: s[0])
        if len(snaps) >= 2:
            last_t, last_v = snaps[-1]
            target = last_t - timedelta(days=30)
            first_t, first_v = min(snaps, key=lambda s: abs((s[0] - target).total_seconds()))
            if first_v and last_v is not None and (last_t - first_t).days >= 7:
                diff = last_v - first_v
                if abs(diff) / first_v >= AUDIENCE_CHANGE and abs(diff) >= AUDIENCE_MIN_ABS:
                    events.append(_event(
                        f"audience:{a.id}:{bucket}", "audience", a,
                        f"{a.name}'s subscribers {'grew' if diff > 0 else 'fell'} {round(abs(diff) / first_v * 100)}%",
                        f"{first_v:,} → {last_v:,} public subscribers between {iso(first_t)[:10]} and {iso(last_t)[:10]}.",
                        "A fast change in audience size often follows a successful post or series; check their recent standouts.",
                        {"label": "See their recent posts", "type": "explorer", "account_id": a.id},
                        previous=f"{first_v:,}", current=f"{last_v:,}",
                        period={"from": iso(first_t), "to": iso(last_t)}))
    return events
