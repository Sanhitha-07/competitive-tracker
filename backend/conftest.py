"""Test setup: every test run uses a fresh, throwaway database, never tracker.db."""
import os
import tempfile
from pathlib import Path

_db = Path(tempfile.gettempdir()) / "competitive-tracker-test.db"
if _db.exists():
    _db.unlink()
os.environ["TRACKER_DB"] = str(_db)
os.environ["YOUTUBE_API_KEY"] = ""  # tests must never call the real API
os.environ.setdefault("MEDIAOPS_DRAFTS_URL", "")
# Tests must never call Meta, Google or Anthropic either.
os.environ["META_ACCESS_TOKEN"] = ""
os.environ["META_IG_USER_ID"] = ""
os.environ["TRENDS_GOOGLE_NEWS"] = "0"
os.environ["TRENDS_GOOGLE_TRENDS"] = "0"
os.environ["ANTHROPIC_API_KEY"] = ""
