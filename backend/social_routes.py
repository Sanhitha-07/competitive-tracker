"""Routes for connecting Instagram, Facebook and X to a workspace.

  GET    /organizations/{org_id}/integrations                      status of each platform (no tokens)
  POST   /organizations/{org_id}/integrations/{platform}/connect   -> {authorize_url} to send the user to
  GET    /oauth/{platform}/callback                                where the platform sends the user back
  POST   /organizations/{org_id}/integrations/{platform}/page      choose the Facebook Page / Instagram account
  DELETE /organizations/{org_id}/integrations/{platform}           disconnect (forget tokens)
  GET    /organizations/{org_id}/profiles/{platform}/suggest?q=     profile suggestions while typing

The callback is the only route without a workspace in the path: the workspace comes from the
single-use `state` that was created for it, never from the browser.
"""
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

import integrations
import secure
import social_http as http
from db import get_session
from models import Organization

router = APIRouter()


def _org(session, org_id):
    if not session.get(Organization, org_id):
        raise HTTPException(404, "Organization not found.")


def _platform(platform):
    try:
        return integrations.get_platform(platform)
    except KeyError:
        raise HTTPException(404, f'"{platform}" has no sign-in. Platforms: {", ".join(integrations.PLATFORMS)}.') from None


def _conn(session, org_id, platform):
    conn = integrations.connection(session, org_id, platform)
    if not conn or conn.status == "disconnected":
        raise HTTPException(404, f"{integrations.PLATFORMS[platform]['label']} isn't connected for this workspace.")
    return conn


@router.get("/organizations/{org_id}/integrations")
def list_integrations(org_id: int, session: Session = Depends(get_session)):
    _org(session, org_id)
    return {"platforms": integrations.describe(session, org_id),
            "not_configured_message": "Not configured — Add API credentials to enable this integration.",
            "setup_doc": "SOCIAL_SETUP.md"}


@router.post("/organizations/{org_id}/integrations/{platform}/connect")
def connect(org_id: int, platform: str, session: Session = Depends(get_session)):
    _org(session, org_id)
    p = _platform(platform)
    try:
        url = integrations.start(session, org_id, platform)
    except integrations.NotReady as exc:
        raise HTTPException(400, str(exc))
    except secure.SecurityError as exc:
        raise HTTPException(400, str(exc))
    return {"authorize_url": url, "platform": platform, "label": p["label"]}


def _back(**params):
    """Send the browser back to the Accounts tab with the outcome in the query string."""
    return RedirectResponse(f"{integrations.frontend_url()}/?{urllib.parse.urlencode(params)}#accounts", status_code=303)


@router.get("/oauth/{platform}/callback", include_in_schema=False)
def callback(platform: str, code: str | None = None, state: str | None = None, error: str | None = None,
             error_description: str | None = None, session: Session = Depends(get_session)):
    _platform(platform)
    if error:
        # The user declined, or the platform refused. Still use up the state so it can't be replayed.
        try:
            secure.take_state(session, state, platform)
        except secure.SecurityError:
            pass
        return _back(connect_error=f"{integrations.PLATFORMS[platform]['label']}: {error_description or error}", platform=platform)
    if not code:
        return _back(connect_error="The platform didn't return an authorization code.", platform=platform)
    try:
        conn = integrations.finish(session, platform, code, state)
    except (secure.SecurityError, integrations.NotReady, http.ApiError) as exc:
        return _back(connect_error=str(exc)[:300], platform=platform)
    if conn.status == "error":
        return _back(connect_error=conn.last_error, platform=platform)
    return _back(connected=platform, status=conn.status)


@router.get("/organizations/{org_id}/profiles/{platform}/suggest")
def suggest_profiles(org_id: int, platform: str, q: str = Query(min_length=2, max_length=100),
                     session: Session = Depends(get_session)):
    """Profiles matching what the user is typing in the Accounts form (logo, name, handle, followers)."""
    _org(session, org_id)
    _platform(platform)
    return integrations.suggest(session, org_id, platform, q)


class PageIn(BaseModel):
    page_id: str = Field(min_length=1, max_length=64)


@router.post("/organizations/{org_id}/integrations/{platform}/page")
def choose_page(org_id: int, platform: str, data: PageIn, session: Session = Depends(get_session)):
    _org(session, org_id)
    _platform(platform)
    conn = _conn(session, org_id, platform)
    try:
        integrations.choose_page(session, conn, data.page_id)
    except http.TokenInvalid as exc:
        integrations.mark_invalid(session, conn, str(exc))
        raise HTTPException(401, str(exc))
    except (ValueError, secure.SecurityError) as exc:
        raise HTTPException(400, str(exc))
    return next(p for p in integrations.describe(session, org_id) if p["id"] == platform)


@router.delete("/organizations/{org_id}/integrations/{platform}", status_code=204)
def disconnect(org_id: int, platform: str, session: Session = Depends(get_session)):
    _org(session, org_id)
    _platform(platform)
    integrations.disconnect(session, _conn(session, org_id, platform))
