"""FastAPI app.

Organizations:      /organizations
Accounts per org:   /organizations/{org_id}/accounts
Fetch (Refresh):    /organizations/{org_id}/fetch
Results:            /organizations/{org_id}/overview, /gaps, /speed, /performance

    run_api.bat      then open http://localhost:8000/docs
"""
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Session, delete, select

import youtube
from analysis import analyse
from db import create_tables, get_session
from fetcher import fetch_org
from models import Competitor, Organization, Post
from performance import compare

app = FastAPI(title="MediaOps Competitive Tracker")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    create_tables()


# ---- Organizations (clients) ----

class OrganizationIn(BaseModel):
    name: str
    category: str = "News"
    window_hours: int = 24


@app.get("/organizations")
def list_organizations(session: Session = Depends(get_session)):
    return session.exec(select(Organization).order_by(Organization.name)).all()


@app.post("/organizations", status_code=201)
def add_organization(data: OrganizationIn, session: Session = Depends(get_session)):
    name = data.name.strip()
    if not name:
        raise HTTPException(400, "Enter an organization name.")
    if session.exec(select(Organization).where(Organization.name == name)).first():
        raise HTTPException(400, "An organization with this name already exists.")
    if not 1 <= data.window_hours <= 24 * 90:
        raise HTTPException(400, "The time window must be between 1 hour and 90 days.")
    org = Organization(name=name, category=data.category.strip() or "News", window_hours=data.window_hours)
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


@app.delete("/organizations/{org_id}", status_code=204)
def remove_organization(org_id: int, session: Session = Depends(get_session)):
    org = _org(session, org_id)
    for c in session.exec(select(Competitor).where(Competitor.org_id == org_id)).all():
        session.exec(delete(Post).where(Post.competitor_id == c.id))
        session.delete(c)
    session.delete(org)
    session.commit()


def _org(session, org_id):
    org = session.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organization not found.")
    return org


# ---- Accounts (ours and competitors') ----

class AccountIn(BaseModel):
    name: str
    platform: Literal["rss", "youtube"] = "rss"
    source: str
    is_us: bool = False


@app.get("/organizations/{org_id}/accounts")
def list_accounts(org_id: int, session: Session = Depends(get_session)):
    _org(session, org_id)
    return session.exec(
        select(Competitor).where(Competitor.org_id == org_id)
        .order_by(Competitor.is_us.desc(), Competitor.name, Competitor.platform)
    ).all()


@app.post("/organizations/{org_id}/accounts", status_code=201)
def add_account(org_id: int, data: AccountIn, session: Session = Depends(get_session)):
    _org(session, org_id)
    name, source = data.name.strip(), data.source.strip()
    if not name or not source:
        raise HTTPException(400, "Enter a name and a link or handle.")
    if data.platform == "rss" and not source.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "The RSS link must start with http:// or https://")
    same_org = select(Competitor).where(Competitor.org_id == org_id, Competitor.platform == data.platform)
    if data.is_us:
        current = session.exec(same_org.where(Competitor.is_us == True)).first()  # noqa: E712
        if current:
            raise HTTPException(400, f'"{current.name}" is already our {_label(data.platform)}. Remove it first.')

    account = Competitor(org_id=org_id, name=name, platform=data.platform, source=source, is_us=data.is_us)
    if data.platform == "youtube":
        try:
            channel = youtube.find_channel(source)  # check the channel exists before saving
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        account.channel_id, account.subscribers = channel["channel_id"], channel["subscribers"]
        account.thumbnail = channel["thumbnail"]
        duplicate = session.exec(same_org.where(Competitor.channel_id == account.channel_id)).first()
    else:
        duplicate = session.exec(same_org.where(Competitor.source == source)).first()
    if duplicate:
        raise HTTPException(400, f"This {_label(data.platform)} is already added as \"{duplicate.name}\".")

    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@app.delete("/organizations/{org_id}/accounts/{account_id}", status_code=204)
def remove_account(org_id: int, account_id: int, session: Session = Depends(get_session)):
    account = session.get(Competitor, account_id)
    if not account or account.org_id != org_id:
        raise HTTPException(404, "Account not found.")
    session.exec(delete(Post).where(Post.competitor_id == account_id))
    session.delete(account)
    session.commit()


@app.get("/youtube/suggest")
def youtube_suggest(q: str):
    """Channels matching what the user is typing, with logo, handle and subscribers."""
    try:
        return youtube.suggest_channels(q)
    except ValueError as exc:
        raise HTTPException(502, str(exc))


def _label(platform):
    return "YouTube channel" if platform == "youtube" else "RSS feed"


# ---- Fetch and results ----

@app.post("/organizations/{org_id}/fetch")
def fetch(org_id: int, session: Session = Depends(get_session)):
    _org(session, org_id)
    return fetch_org(session, org_id)


def _load(session, org_id):
    org = _org(session, org_id)
    accounts = session.exec(select(Competitor).where(Competitor.org_id == org_id)).all()
    ids = [a.id for a in accounts]
    posts = session.exec(select(Post).where(Post.competitor_id.in_(ids))).all() if ids else []
    return org, accounts, posts


@app.get("/organizations/{org_id}/results")
def results(org_id: int, session: Session = Depends(get_session)):
    """Everything the dashboard needs in one call."""
    org, accounts, posts = _load(session, org_id)
    news = analyse(posts, accounts, window_hours=org.window_hours)
    perf = compare(accounts, posts, gaps_count=len(news["gaps"]))
    return {"organization": org, **news, "performance": perf}


@app.get("/organizations/{org_id}/overview")
def get_overview(org_id: int, session: Session = Depends(get_session)):
    org, accounts, posts = _load(session, org_id)
    return analyse(posts, accounts, window_hours=org.window_hours)["overview"]


@app.get("/organizations/{org_id}/gaps")
def get_gaps(org_id: int, session: Session = Depends(get_session)):
    org, accounts, posts = _load(session, org_id)
    return analyse(posts, accounts, window_hours=org.window_hours)["gaps"]


@app.get("/organizations/{org_id}/speed")
def get_speed(org_id: int, session: Session = Depends(get_session)):
    org, accounts, posts = _load(session, org_id)
    return analyse(posts, accounts, window_hours=org.window_hours)["speed"]


@app.get("/organizations/{org_id}/performance")
def get_performance(org_id: int, session: Session = Depends(get_session)):
    org, accounts, posts = _load(session, org_id)
    gaps = analyse(posts, accounts, window_hours=org.window_hours)["gaps"]
    return compare(accounts, posts, gaps_count=len(gaps))
