"""Made-up sample data, so the analysis can be tested before the fetcher is ready.
Channel names are placeholders, not real channels.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as Row

COMPETITORS = [
    Row(id=1, name="Our Channel", rss_url="https://our-channel.example/rss", is_us=True),
    Row(id=2, name="Channel A", rss_url="https://channel-a.example/rss", is_us=False),
    Row(id=3, name="Channel B", rss_url="https://channel-b.example/rss", is_us=False),
    Row(id=4, name="Channel C", rss_url="https://channel-c.example/rss", is_us=False),
    Row(id=5, name="Channel D", rss_url="https://channel-d.example/rss", is_us=False),
]


def make_posts(now=None):
    now = now or datetime.now(timezone.utc)

    def at(hours_ago, minutes=0):
        return now - timedelta(hours=hours_ago) + timedelta(minutes=minutes)

    raw = [
        # Gap: 3 competitors, not us -> P1
        (2, "Heavy rain alert for Hyderabad tonight, IMD issues orange alert", at(5)),
        (3, "Hyderabad on alert as heavy rain expected tonight", at(5, 12)),
        (4, "IMD orange alert: heavy rain likely in Hyderabad tonight", at(5, 30)),
        # Gap: 2 competitors, not us -> P2
        (3, "Gold price jumps Rs 800 in a single day", at(3)),
        (5, "Gold prices jump by Rs 800 today", at(3, 20)),
        # Speed: Channel B first, we are 39 min late
        (3, "State cabinet approves new metro line to airport", at(8)),
        (2, "Cabinet nod for airport metro line", at(8, 18)),
        (1, "State cabinet approves airport metro line project", at(8, 39)),
        # Speed: we were first
        (1, "India announce squad for ODI series against New Zealand", at(6)),
        (5, "India squad for New Zealand ODI series announced", at(6, 25)),
        # Only 1 competitor -> not a gap
        (4, "Local temple festival draws large crowds", at(2)),
        # Shares a word with the rain story but is a different story -> must not join it
        (2, "Hyderabad traffic diversions for Sunday marathon", at(4)),
        # Our own story nobody else covered
        (1, "Interview with district collector on school safety", at(1)),
        # Older than 24 hours -> ignored
        (2, "Heavy rain alert for Hyderabad tonight", at(30)),
    ]
    return [
        Row(id=i, competitor_id=c, title=t, link=f"https://example.com/story/{i}", published_at=p)
        for i, (c, t, p) in enumerate(raw, start=1)
    ]
