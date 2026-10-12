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
