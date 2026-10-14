"""Reads settings from the .env file next to this one (kept out of the code and out of Git)."""
import os
from pathlib import Path

_env = Path(__file__).with_name(".env")
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
# Our own cap on YouTube units per day (YouTube's free limit is 10,000).
YOUTUBE_DAILY_BUDGET = int(os.environ.get("YOUTUBE_DAILY_BUDGET", "9000"))
# Optional: MediaOps endpoint that accepts Draft Packages. Empty = copy/paste handoff.
MEDIAOPS_DRAFTS_URL = os.environ.get("MEDIAOPS_DRAFTS_URL", "")
MEDIAOPS_API_TOKEN = os.environ.get("MEDIAOPS_API_TOKEN", "")

# Meta Graph API (Instagram + Facebook). See SETUP.md for how to get these.
# META_ACCESS_TOKEN: a long-lived user or system-user token for your Meta app.
# META_IG_USER_ID:   YOUR Instagram professional account ID. Business Discovery reads other
#                    accounts "through" it, so it's required for Instagram.
META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "")
META_IG_USER_ID = os.environ.get("META_IG_USER_ID", "")
META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v25.0")
# Our own cap on Graph API calls per hour (Meta's limits depend on the app and token).
META_HOURLY_BUDGET = int(os.environ.get("META_HOURLY_BUDGET", "180"))

# Internet trends. Google News search RSS is for personal, non-commercial use under Google's
# terms; set TRENDS_GOOGLE_NEWS=0 to switch it off for commercial deployments.
TRENDS_GOOGLE_NEWS = os.environ.get("TRENDS_GOOGLE_NEWS", "1") != "0"
TRENDS_GOOGLE_TRENDS = os.environ.get("TRENDS_GOOGLE_TRENDS", "1") != "0"

# Optional AI briefing (Claude). Empty = plain-language briefing built from rules only.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "claude-opus-5-5")
