"""Check the analysis on REAL news: reads live RSS feeds, runs the analysis, prints the results.
Nothing is saved to the database. This is only for checking the matching on real headlines.

    python check_real_data.py

Edit FEEDS to change channels. Exactly one feed must have is_us=True.
For this test, one public site plays "us", because our own channel's feed is not added yet.
"""
import calendar
import json
import sys
from datetime import datetime, timezone
from types import SimpleNamespace as Row

# Print Indian-language headlines and curly quotes correctly in the Windows terminal.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import feedparser
    from analysis import analyse, group_stories, recent_posts
except ModuleNotFoundError as exc:
    sys.exit(
        f"Missing package: {exc.name}\n"
        "You are running the computer's main Python, not the project's env.\n"
        "Fix: double-click check_real_data.bat, or run:\n"
        "    env\\Scripts\\python.exe check_real_data.py"
    )

FEEDS = [
    # (name, rss_url, is_us)
    ("The Hindu (as us)", "https://www.thehindu.com/news/national/feeder/default.rss", True),
    ("Indian Express", "https://indianexpress.com/feed/", False),
    ("Hindustan Times", "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml", False),
    ("Times of India", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms", False),
    ("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories", False),
    ("India Today", "https://www.indiatoday.in/rss/home", False),
]


def read_feed(url):
    feed = feedparser.parse(url, agent="Mozilla/5.0 CompetitiveTracker")
    items = []
    for e in feed.entries:
        if not e.get("title") or not e.get("link"):
            continue
        t = e.get("published_parsed") or e.get("updated_parsed")
        when = datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc) if t else datetime.now(timezone.utc)
        items.append((e.title.strip(), e.link, when))
    return items


competitors, posts = [], []
print("=== FEEDS ===")
for cid, (name, url, is_us) in enumerate(FEEDS, start=1):
    competitors.append(Row(id=cid, name=name, rss_url=url, is_us=is_us))
    try:
        items = read_feed(url)
    except Exception as exc:  # one bad feed must not stop the others
        print(f"  FAILED  {name}: {exc}")
        continue
    print(f"  {len(items):>3} stories  {name}")
    for title, link, when in items:
        posts.append(Row(id=len(posts) + 1, competitor_id=cid, title=title, link=link, published_at=when))

names = {c.id: c.name for c in competitors}
groups = [g for g in group_stories(recent_posts(posts)) if len({p.competitor_id for p in g}) > 1]

print(f"\n=== MATCHED STORIES ({len(groups)}) - check each group is really ONE story ===")
for i, g in enumerate(groups, start=1):
    print(f"\nGroup {i}:")
    for p in sorted(g, key=lambda p: p.published_at):
        ist = p.published_at.astimezone(timezone.utc).strftime("%H:%M UTC")
        print(f"   {ist}  [{names[p.competitor_id]}] {p.title}")

result = analyse(posts, competitors)
print("\n=== OVERVIEW ===")
print(json.dumps(result["overview"], indent=2))
print(f"\n=== COVERAGE GAPS ({len(result['gaps'])}) ===")
for g in result["gaps"]:
    print(f"  {g['priority']}  {g['title']}\n      covered by: {', '.join(g['covered_by'])}")
print(f"\n=== SPEED ({len(result['speed'])}) ===")
for r in result["speed"]:
    status = "WE WERE FIRST" if r["we_were_first"] else f"{r['delay_minutes']} min late (first: {r['first_by']})"
    print(f"  {status:<40} {r['title']}")
