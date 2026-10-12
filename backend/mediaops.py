"""Hand an opportunity to MediaOps as a Draft Package.

Only a DRAFT is created. Pre-air certification, approval, scheduling and publishing stay in
MediaOps under its own users and permissions; this tracker never publishes or approves anything.

Two modes:
  api   MEDIAOPS_DRAFTS_URL (+ MEDIAOPS_API_TOKEN) set in backend\\.env: the draft is POSTed there
        and the returned id is stored on the opportunity.
  copy  not configured: the draft text is returned for the user to paste into
        Draft Packages > Create, and they can paste the new draft's id/link back here.
"""
import json
import urllib.error
import urllib.request

from config import MEDIAOPS_API_TOKEN, MEDIAOPS_DRAFTS_URL


def configured():
    return bool(MEDIAOPS_DRAFTS_URL)


def draft_payload(opp, org, platforms):
    b = opp.brief or {}
    return {
        "heading": b.get("working_title", opp.title),
        "status": "draft",
        "organization": org.name,
        "platforms": platforms,
        "body": b,
        "source": {"app": "competitive-tracker", "opportunity_id": opp.id, "kind": opp.kind,
                   "key": opp.key},
    }


def send_draft(payload, user_token=None):
    """POST the draft to MediaOps. The caller's own token is preferred, so MediaOps applies that
    user's permissions; the server token is only a fallback for single-user demos."""
    token = user_token or MEDIAOPS_API_TOKEN
    req = urllib.request.Request(
        MEDIAOPS_DRAFTS_URL, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            body = json.load(res)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise PermissionError("MediaOps refused the draft: you don't have permission to create drafts there.") from exc
        raise ValueError(f"MediaOps returned an error ({exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Can't reach MediaOps: {exc.reason}") from exc
    return str(body.get("id") or body.get("draft_id") or body.get("url") or "")
