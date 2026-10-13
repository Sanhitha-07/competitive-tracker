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

# ---- Instagram, Facebook and X (all optional: the app starts without them) ----
# Read when used, not at import, so a changed .env takes effect after a restart and tests can set them.
# See SOCIAL_SETUP.md and .env.example for what each one is and where to get it.


def setting(name, default=""):
    return os.environ.get(name, default).strip()


SOCIAL_SETTINGS = {
    # One Meta developer app serves both Facebook Pages and Instagram (Instagram API with Facebook Login).
    "META_APP_ID": "Meta app ID (developers.facebook.com > your app > App settings > Basic)",
    "META_APP_SECRET": "Meta app secret (same page; keep it only in backend/.env)",
    "X_CLIENT_ID": "X OAuth 2.0 Client ID (developer.x.com > your app > Keys and tokens)",
    "X_CLIENT_SECRET": "X OAuth 2.0 Client Secret (confidential 'Web App' clients only)",
    "TOKEN_ENCRYPTION_KEY": "Key used to encrypt stored access tokens (generate with the command in SOCIAL_SETUP.md)",
}
META_GRAPH_VERSION_DEFAULT = "v26.0"  # latest Graph API version as of July 2026; override with META_GRAPH_VERSION
PUBLIC_API_URL_DEFAULT = "http://localhost:8000"  # where Meta and X send the user back (the OAuth redirect)
FRONTEND_URL_DEFAULT = "http://localhost:5173"    # where the user lands after connecting
