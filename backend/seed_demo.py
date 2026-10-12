"""Create the demo clients and fetch their real data (RSS + YouTube).

    python seed_demo.py

Deletes everything in the database first. The "us" accounts are real public channels
standing in for a client, for demo purposes only.
"""
import sys

from sqlmodel import Session, delete

import youtube
from db import create_tables, engine
from fetcher import fetch_org
from models import Competitor, Organization, Post

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEMO = [
    {
        "name": "Demo News Network", "category": "News", "window_hours": 24,
        "accounts": [
            ("The Hindu (demo: us)", "rss", "https://www.thehindu.com/news/national/feeder/default.rss", True),
            ("The Hindu (demo: us)", "youtube", "@thehinduofficial", True),
            ("Indian Express", "rss", "https://indianexpress.com/section/india/feed/", False),
            ("Indian Express", "youtube", "@indianexpress", False),
            ("Hindustan Times", "rss", "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml", False),
            ("Hindustan Times", "youtube", "@ht-videos", False),
            ("NDTV", "rss", "https://feeds.feedburner.com/ndtvnews-india-news", False),
            ("NDTV", "youtube", "@ndtv", False),
            ("Times of India", "rss", "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms", False),
            ("Times of India", "youtube", "@timesofindia", False),
        ],
    },
    {
        "name": "Demo Fitness Creator", "category": "Fitness", "window_hours": 24 * 30,
        "accounts": [
            ("Fit Tuber (demo: us)", "youtube", "@FitTuber", True),
            ("Jeff Nippard", "youtube", "@JeffNippard", False),
            ("ATHLEAN-X", "youtube", "@athleanx", False),
            ("Chloe Ting", "youtube", "@chloeting", False),
        ],
    },
    {
        "name": "Demo Tech Creator", "category": "Technology", "window_hours": 24 * 30,
        "accounts": [
            ("Technical Guruji (demo: us)", "youtube", "@TechnicalGuruji", True),
            ("Trakin Tech", "youtube", "@TrakinTech", False),
            ("Geekyranjit", "youtube", "@GeekyRanjit", False),
            ("Mrwhosetheboss", "youtube", "@mrwhosetheboss", False),
            ("Marques Brownlee", "youtube", "@mkbhd", False),
        ],
    },
]

create_tables()
with Session(engine) as s:
    s.exec(delete(Post))
    s.exec(delete(Competitor))
    s.exec(delete(Organization))
    s.commit()

    for d in DEMO:
        org = Organization(name=d["name"], category=d["category"], window_hours=d["window_hours"])
        s.add(org)
        s.commit()
        s.refresh(org)
        for name, platform, source, is_us in d["accounts"]:
            account = Competitor(org_id=org.id, name=name, platform=platform, source=source, is_us=is_us)
            if platform == "youtube":
                ch = youtube.find_channel(source)
                account.channel_id, account.subscribers = ch["channel_id"], ch["subscribers"]
            s.add(account)
        s.commit()

        print(f"\n{org.name}: fetching…")
        result = fetch_org(s, org.id)
        for a in result["accounts"]:
            status = f"ERROR {a['error']}" if a["error"] else f"{a['found']} found, {a['added']} saved"
            print(f"   {a['platform']:<8} {a['account']:<30} {status}")

print("\nDemo data ready. Start run_api.bat and the UI.")
