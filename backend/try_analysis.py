"""Run the analysis on sample data and print the results.

    python try_analysis.py
"""
import json
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from analysis import analyse, group_stories, recent_posts
from sample_data import COMPETITORS, make_posts

now = datetime.now(timezone.utc)
posts = make_posts(now)
names = {c.id: c.name for c in COMPETITORS}

print("=== STORY GROUPS (check these look right) ===")
for i, g in enumerate(group_stories(recent_posts(posts, now)), start=1):
    print(f"\nStory {i}:")
    for p in g:
        print(f"   [{names[p.competitor_id]}] {p.title}")

result = analyse(posts, COMPETITORS, now)
print("\n=== OVERVIEW ===")
print(json.dumps(result["overview"], indent=2))
print("\n=== COVERAGE GAPS ===")
print(json.dumps(result["gaps"], indent=2))
print("\n=== SPEED ===")
print(json.dumps(result["speed"], indent=2))
