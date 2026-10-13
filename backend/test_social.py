"""Instagram, Facebook and X integration checks. Run with:  python -m pytest -q

Code-level tests only: every platform response here is a MOCK (see FakePlatforms). No real request
is made, and nothing here shows that a real Meta or X app works; that needs real credentials.
"""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import fetcher
import integrations
import main
import meta_api
import social_http
import x_api
from db import engine
from models import Competitor, OAuthState, Post, SocialConnection

META_ENV = {"META_APP_ID": "test-app", "META_APP_SECRET": "test-secret"}
X_ENV = {"X_CLIENT_ID": "test-client", "X_CLIENT_SECRET": "test-x-secret"}


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def no_network(monkeypatch):
    """Fail the test if anything tries to reach a platform."""
    def boom(*a, **k):
        raise AssertionError("A platform API was called")
    monkeypatch.setattr(social_http, "transport", boom)


@pytest.fixture
def configured(monkeypatch):
    for k, v in {**META_ENV, **X_ENV, "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode()}.items():
        monkeypatch.setenv(k, v)


class FakePlatforms:
    """Mocked Meta and X responses, routed by URL. Records every call."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body))
        for needle, reply in self.routes:
            if needle in url:
                status, data = reply(url, body) if callable(reply) else reply
                return status, json.dumps(data), {}
        raise AssertionError(f"Unexpected request: {method} {url}")


def _org(client, name):
    r = client.post("/organizations", json={"name": name, "category": "fitness"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _state(url):
    return parse_qs(urlparse(url).query)["state"][0]


# ---- not configured: visible, honest, and silent ----

def test_not_configured_is_shown_and_never_calls_apis(client, no_network, monkeypatch):
    for k in [*META_ENV, *X_ENV, "TOKEN_ENCRYPTION_KEY"]:
        monkeypatch.delenv(k, raising=False)
    org = _org(client, "Social Off")
    data = client.get(f"/organizations/{org}/integrations").json()
    assert {p["id"] for p in data["platforms"]} == {"instagram", "facebook", "x"}
    for p in data["platforms"]:
        assert p["state"] == "not_configured" and p["connection"] is None and "TOKEN_ENCRYPTION_KEY" in p["missing"]
        assert p["setup"] and p["redirect_uri"].endswith(f"/oauth/{p['id']}/callback")
    assert data["not_configured_message"].startswith("Not configured")
    r = client.post(f"/organizations/{org}/integrations/instagram/connect")
    assert r.status_code == 400 and "META_APP_ID" in r.json()["detail"]
    with Session(engine) as s:
        assert not s.exec(select(OAuthState).where(OAuthState.org_id == org)).all()  # no sign-in started

    # A competitor can still be added: saved as Unverified, no API call.
    r = client.post(f"/organizations/{org}/accounts", json={"name": "Nat Geo", "platform": "instagram",
                                                            "source": "https://www.instagram.com/natgeo/"})
    assert r.status_code == 201 and r.json()["verified"] is False and r.json()["source"] == "natgeo"
    dup = client.post(f"/organizations/{org}/accounts", json={"name": "NG", "platform": "instagram", "source": "@NatGeo"})
    assert dup.status_code == 400 and "already added" in dup.json()["detail"]
    bad = client.post(f"/organizations/{org}/accounts", json={"name": "x", "platform": "x", "source": "https://facebook.com/abc"})
    assert bad.status_code == 400 and "isn't a X link" in bad.json()["detail"]
    row = next(a for a in client.get(f"/organizations/{org}/accounts").json() if a["platform"] == "instagram")
    assert row["health"]["state"] == "not_configured" and row["public_url"] == "https://www.instagram.com/natgeo/"

    # Refresh skips it with a reason, no error, no posts.
    with Session(engine) as s:
        res = fetcher.fetch_org(s, org)
    ig = next(a for a in res["accounts"] if a["platform"] == "instagram")
    assert ig["error"] is None and "Not configured" in ig["skipped"] and res["added"] == 0
    d = client.get(f"/organizations/{org}/dashboard").json()
    assert all(not s["configured"] and s["total"] == 0 for s in d["social"])


def test_unknown_platform_and_bad_key(client, monkeypatch):
    org = _org(client, "Social Bad")
    assert client.post(f"/organizations/{org}/integrations/myspace/connect").status_code == 404
    for k, v in {**META_ENV, "TOKEN_ENCRYPTION_KEY": "not-a-key"}.items():
        monkeypatch.setenv(k, v)
    fb = next(p for p in client.get(f"/organizations/{org}/integrations").json()["platforms"] if p["id"] == "facebook")
    assert fb["state"] == "not_configured" and "TOKEN_ENCRYPTION_KEY (invalid)" in fb["missing"]


# ---- sign-in links and state ----

def test_connect_builds_official_sign_in_urls(client, configured, no_network):
    org = _org(client, "Social Urls")
    fb = client.post(f"/organizations/{org}/integrations/facebook/connect").json()["authorize_url"]
    q = parse_qs(urlparse(fb).query)
    assert fb.startswith("https://www.facebook.com/v26.0/dialog/oauth")
    assert q["client_id"] == ["test-app"] and q["scope"] == ["pages_show_list,pages_read_engagement"]
    assert q["redirect_uri"] == ["http://localhost:8000/oauth/facebook/callback"]
    xu = client.post(f"/organizations/{org}/integrations/x/connect").json()["authorize_url"]
    xq = parse_qs(urlparse(xu).query)
    assert xu.startswith("https://x.com/i/oauth2/authorize") and xq["code_challenge_method"] == ["S256"]
    assert xq["scope"] == ["tweet.read users.read offline.access"]
    with Session(engine) as s:
        st = s.exec(select(OAuthState).where(OAuthState.state == _state(xu))).one()
        assert st.org_id == org and st.platform == "x" and st.code_verifier


def test_callback_rejects_bad_reused_and_expired_state(client, configured, no_network):
    org = _org(client, "Social State")
    r = client.get("/oauth/facebook/callback", params={"code": "c", "state": "forged"})
    assert r.status_code == 303 and "connect_error" in r.headers["location"]
    url = client.post(f"/organizations/{org}/integrations/facebook/connect").json()["authorize_url"]
    wrong = client.get("/oauth/x/callback", params={"code": "c", "state": _state(url)})  # state for another platform
    assert "connect_error" in wrong.headers["location"]
    url = client.post(f"/organizations/{org}/integrations/facebook/connect").json()["authorize_url"]
    with Session(engine) as s:
        st = s.exec(select(OAuthState).where(OAuthState.state == _state(url))).one()
        st.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        s.add(st)
        s.commit()
    old = client.get("/oauth/facebook/callback", params={"code": "c", "state": _state(url)})
    assert "expired" in old.headers["location"]
    denied = client.get("/oauth/facebook/callback", params={"error": "access_denied", "state": "x"})
    assert "access_denied" in denied.headers["location"]


# ---- Meta: Facebook Pages and Instagram ----

def _meta_routes(pages):
    return FakePlatforms([
        ("oauth/access_token", lambda url, body: (200, {"access_token": "LONG-USER" if "fb_exchange_token" in url else "SHORT",
                                                       "expires_in": 5184000})),
        ("me/permissions", (200, {"data": [{"permission": "pages_show_list", "status": "granted"}]})),
        ("me/accounts", (200, {"data": pages})),
    ])


def test_facebook_sign_in_page_choice_and_encrypted_tokens(client, configured, monkeypatch):
    org = _org(client, "Social FB")
    fake = _meta_routes([{"id": "111", "name": "Our Page", "access_token": "PAGE-TOKEN-111"},
                         {"id": "222", "name": "Other Page", "access_token": "PAGE-TOKEN-222"}])
    monkeypatch.setattr(social_http, "transport", fake)
    url = client.post(f"/organizations/{org}/integrations/facebook/connect").json()["authorize_url"]
    r = client.get("/oauth/facebook/callback", params={"code": "abc", "state": _state(url)})
    assert "connected=facebook" in r.headers["location"] and "needs_page" in r.headers["location"]
    fb = next(p for p in client.get(f"/organizations/{org}/integrations").json()["platforms"] if p["id"] == "facebook")
    assert fb["state"] == "needs_page" and [c["id"] for c in fb["connection"]["choices"]] == ["111", "222"]
    assert "PAGE-TOKEN" not in json.dumps(fb) and "LONG-USER" not in json.dumps(fb)  # no tokens to the browser
    r = client.post(f"/organizations/{org}/integrations/facebook/page", json={"page_id": "111"})
    assert r.status_code == 200 and r.json()["state"] == "connected" and r.json()["connection"]["account_name"] == "Our Page"
    with Session(engine) as s:
        conn = integrations.connection(s, org, "facebook")
        assert conn.access_token_enc and "LONG-USER" not in conn.access_token_enc  # encrypted at rest
        assert "PAGE-TOKEN" not in (conn.page_token_enc or "") and integrations.context(s, org, "facebook").page_token == "PAGE-TOKEN-111"
    assert client.post(f"/organizations/{org}/integrations/facebook/page", json={"page_id": "999"}).status_code == 400

    # Another workspace can't touch this connection.
    other = _org(client, "Social FB Other")
    assert client.delete(f"/organizations/{other}/integrations/facebook").status_code == 404
    assert client.delete(f"/organizations/{org}/integrations/facebook").status_code == 204
    with Session(engine) as s:
        conn = integrations.connection(s, org, "facebook")
        assert conn.status == "disconnected" and conn.access_token_enc is None and conn.page_token_enc is None


def test_instagram_requires_a_linked_professional_account(client, configured, monkeypatch):
    org = _org(client, "Social IG")
    monkeypatch.setattr(social_http, "transport", _meta_routes([{"id": "1", "name": "Page", "access_token": "T"}]))
    url = client.post(f"/organizations/{org}/integrations/instagram/connect").json()["authorize_url"]
    r = client.get("/oauth/instagram/callback", params={"code": "abc", "state": _state(url)})
    assert "professional+account" in r.headers["location"]  # no linked Instagram account: not connected

    monkeypatch.setattr(social_http, "transport", _meta_routes([
        {"id": "1", "name": "Page", "access_token": "T", "instagram_business_account": {"id": "1784", "username": "ourbrand"}}]))
    url = client.post(f"/organizations/{org}/integrations/instagram/connect").json()["authorize_url"]
    r = client.get("/oauth/instagram/callback", params={"code": "abc", "state": _state(url)})
    assert "connected=instagram" in r.headers["location"]
    ig = next(p for p in client.get(f"/organizations/{org}/integrations").json()["platforms"] if p["id"] == "instagram")
    assert ig["state"] == "connected" and ig["connection"]["username"] == "ourbrand"

    # Competitor via Business Discovery (mocked), then a refresh saves its posts once.
    media = [{"id": "m1", "caption": "Leg day #fitness\nmore", "media_type": "VIDEO", "media_product_type": "REELS",
              "timestamp": "2026-10-01T10:00:00+0000", "permalink": "https://www.instagram.com/reel/m1/", "comments_count": 4},
             {"id": "m2", "caption": "Protein oats", "media_type": "IMAGE", "media_product_type": "FEED",
              "timestamp": "2026-10-02T10:00:00+0000", "permalink": "https://www.instagram.com/p/m2/", "like_count": 50,
              "comments_count": 2, "media_url": "https://cdn/x.jpg"}]
    monkeypatch.setattr(social_http, "transport", FakePlatforms([("1784", (200, {"business_discovery": {
        "id": "999", "username": "rival", "followers_count": 5000, "media": {"data": media}}}))]))
    r = client.post(f"/organizations/{org}/accounts", json={"name": "Rival", "platform": "instagram", "source": "@rival"})
    assert r.status_code == 201 and r.json()["verified"] is True and r.json()["external_id"] == "999"
    with Session(engine) as s:
        for _ in range(2):
            res = fetcher.fetch_org(s, org)
        posts = s.exec(select(Post).join(Competitor).where(Competitor.org_id == org)).all()
    assert res["accounts"][0]["error"] is None and len(posts) == 2  # no duplicates on the second refresh
    reel = next(p for p in posts if p.link.endswith("/m1/"))
    assert reel.format == "reel" and reel.title == "Leg day #fitness" and reel.tags == ["fitness"]
    assert reel.likes is None and reel.views is None  # hidden likes stay unknown, never 0


def test_facebook_competitor_without_ppca_stays_unverified(client, configured, monkeypatch):
    org = _org(client, "Social FB PPCA")
    with Session(engine) as s:
        s.add(SocialConnection(org_id=org, platform="facebook", status="connected", external_id="111",
                               access_token_enc=__import__("secure").encrypt("USER"),
                               page_token_enc=__import__("secure").encrypt("PAGE")))
        s.commit()
    monkeypatch.setattr(social_http, "transport", FakePlatforms([("rivalpage", (400, {"error": {
        "code": 10, "message": "Requires Page Public Content Access"}}))]))
    r = client.post(f"/organizations/{org}/accounts", json={"name": "Rival", "platform": "facebook",
                                                            "source": "https://www.facebook.com/rivalpage"})
    assert r.status_code == 201 and r.json()["verified"] is False and "Page Public Content Access" in r.json()["note"]


# ---- X ----

def _x_routes(posts_reply=None):
    return FakePlatforms([
        ("oauth2/token", lambda url, body: (200, {"access_token": "XA-" + ("R" if b"refresh_token" in body else "1"),
                                                 "refresh_token": "XR-2", "expires_in": 7200,
                                                 "scope": "tweet.read users.read offline.access"})),
        ("users/me", (200, {"data": {"id": "42", "name": "Us", "username": "us"}})),
        ("users/by/username/", lambda url, body: (200, {"data": {
            "id": "77" if url.split("?")[0].endswith("/rival") else "78", "username": url.split("?")[0].rsplit("/", 1)[1],
            "public_metrics": {"followers_count": 900}}})),
        ("/tweets", posts_reply or (200, {"data": [
            {"id": "t1", "text": "Kettlebell tips #fitness", "created_at": "2026-10-05T09:00:00.000Z",
             "public_metrics": {"impression_count": 1200, "like_count": 30, "reply_count": 3, "retweet_count": 2}}],
            "meta": {}})),
    ])


def test_x_sign_in_refresh_and_collection(client, configured, monkeypatch):
    org = _org(client, "Social X")
    fake = _x_routes()
    monkeypatch.setattr(social_http, "transport", fake)
    url = client.post(f"/organizations/{org}/integrations/x/connect").json()["authorize_url"]
    r = client.get("/oauth/x/callback", params={"code": "abc", "state": _state(url)})
    assert "connected=x" in r.headers["location"]
    token_call = next(c for c in fake.calls if "oauth2/token" in c[1])
    assert token_call[2]["Authorization"].startswith("Basic ") and b"code_verifier=" in token_call[3]

    r = client.post(f"/organizations/{org}/accounts", json={"name": "Rival", "platform": "x", "source": "https://x.com/rival"})
    assert r.status_code == 201 and r.json()["verified"] and r.json()["subscribers"] == 900
    with Session(engine) as s:  # token expired: refreshed (and rotated) before collecting
        conn = integrations.connection(s, org, "x")
        conn.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        s.add(conn)
        s.commit()
        res = fetcher.fetch_org(s, org)
        assert integrations.context(s, org, "x").token == "XA-R"
        post = s.exec(select(Post).join(Competitor).where(Competitor.org_id == org)).one()
    assert res["accounts"][0]["added"] == 1
    assert post.views == 1200 and post.likes == 30 and post.comments == 3 and post.shares == 2
    assert post.link == "https://x.com/rival/status/t1"


def test_x_revoked_token_marks_connection_and_skips(client, configured, monkeypatch):
    org = _org(client, "Social X Revoked")
    monkeypatch.setattr(social_http, "transport", _x_routes())
    url = client.post(f"/organizations/{org}/integrations/x/connect").json()["authorize_url"]
    client.get("/oauth/x/callback", params={"code": "abc", "state": _state(url)})
    client.post(f"/organizations/{org}/accounts", json={"name": "Rival", "platform": "x", "source": "rival"})
    client.post(f"/organizations/{org}/accounts", json={"name": "Rival2", "platform": "x", "source": "rival2"})
    fake = _x_routes(posts_reply=(401, {"title": "Unauthorized"}))
    monkeypatch.setattr(social_http, "transport", fake)
    with Session(engine) as s:
        res = fetcher.fetch_org(s, org)
        assert integrations.connection(s, org, "x").status == "expired"
    first, second = res["accounts"]
    assert first["error"] and "Reconnect" in first["error"]
    assert second["skipped"] and "Reconnect" in second["skipped"]  # no second call with a dead token
    x = next(p for p in client.get(f"/organizations/{org}/integrations").json()["platforms"] if p["id"] == "x")
    assert x["state"] == "expired"


# ---- error meanings and retries ----

def test_error_classification_and_retry(monkeypatch):
    assert isinstance(meta_api.classify(400, {"error": {"code": 190}}), social_http.TokenInvalid)
    assert isinstance(meta_api.classify(400, {"error": {"code": 4}}), social_http.RateLimited)
    assert isinstance(meta_api.classify(403, {"error": {"code": 200}}), social_http.NotPermitted)
    assert isinstance(x_api.classify(402, {}), social_http.NotPermitted)
    assert isinstance(x_api.classify(429, {}), social_http.RateLimited)
    replies = iter([(503, "{}", {}), (200, '{"ok": 1}', {})])
    monkeypatch.setattr(social_http, "transport", lambda *a: next(replies))
    assert social_http.request("GET", "https://x.test", classify=x_api.classify, sleep=lambda s: None) == {"ok": 1}
    monkeypatch.setattr(social_http, "transport", lambda *a: (401, "{}", {}))
    with pytest.raises(social_http.TokenInvalid):
        social_http.request("GET", "https://x.test", classify=x_api.classify, sleep=lambda s: None)


# ---- profile suggestions while typing ----

def test_suggest_without_setup_makes_no_calls(client, no_network, monkeypatch):
    for k in [*META_ENV, *X_ENV, "TOKEN_ENCRYPTION_KEY"]:
        monkeypatch.delenv(k, raising=False)
    org = _org(client, "Suggest Off")
    r = client.get(f"/organizations/{org}/profiles/instagram/suggest", params={"q": "natgeo"}).json()
    assert r == {"available": False, "results": [], "note": "Integration is not configured yet. Contact your administrator to enable it."}
    assert client.get(f"/organizations/{org}/profiles/tiktok/suggest", params={"q": "abc"}).status_code == 404


def test_suggest_instagram_exact_lookup_cached_and_name_filled(client, configured, monkeypatch):
    org = _org(client, "Suggest IG")
    monkeypatch.setattr(social_http, "transport", _meta_routes([
        {"id": "1", "name": "Page", "access_token": "T", "instagram_business_account": {"id": "1784", "username": "ourbrand"}}]))
    url = client.post(f"/organizations/{org}/integrations/instagram/connect").json()["authorize_url"]
    client.get("/oauth/instagram/callback", params={"code": "abc", "state": _state(url)})
    fake = FakePlatforms([("1784", (200, {"business_discovery": {
        "id": "555", "username": "natgeo", "name": "National Geographic", "followers_count": 280000000,
        "profile_picture_url": "https://cdn/ng.jpg"}}))])
    monkeypatch.setattr(social_http, "transport", fake)
    r = client.get(f"/organizations/{org}/profiles/instagram/suggest", params={"q": "@NatGeo"}).json()
    assert r["available"] and r["mode"] == "exact" and r["results"][0]["display_name"] == "National Geographic"
    client.get(f"/organizations/{org}/profiles/instagram/suggest", params={"q": "natgeo"})
    assert len(fake.calls) == 1  # second identical lookup came from the cache
    added = client.post(f"/organizations/{org}/accounts", json={"platform": "instagram", "source": "natgeo"}).json()
    assert added["name"] == "National Geographic" and added["thumbnail"] == "https://cdn/ng.jpg"
    assert added["subscribers"] == 280000000 and added["verified"] is True
    assert client.post(f"/organizations/{org}/accounts", json={"platform": "youtube", "source": "@x"}).status_code == 400


def test_suggest_x_falls_back_to_exact_lookup(client, configured, monkeypatch):
    org = _org(client, "Suggest X")
    monkeypatch.setattr(social_http, "transport", _x_routes())
    url = client.post(f"/organizations/{org}/integrations/x/connect").json()["authorize_url"]
    client.get("/oauth/x/callback", params={"code": "abc", "state": _state(url)})
    fake = FakePlatforms([("users/search", (403, {"title": "Forbidden", "detail": "Pro access required"})),
                          ("users/by/username/rival", (200, {"data": {"id": "77", "username": "rival", "name": "Rival Co"}}))])
    monkeypatch.setattr(social_http, "transport", fake)
    r = client.get(f"/organizations/{org}/profiles/x/suggest", params={"q": "rival"}).json()
    assert r["mode"] == "exact" and [p["source"] for p in r["results"]] == ["rival"]
    fake2 = FakePlatforms([("users/search", (200, {"data": [{"id": "1", "username": "kbell", "name": "Kettlebell Kings"},
                                                             {"id": "2", "username": "kb_daily", "name": "KB Daily"}]}))])
    monkeypatch.setattr(social_http, "transport", fake2)
    r = client.get(f"/organizations/{org}/profiles/x/suggest", params={"q": "kettlebell"}).json()
    assert r["mode"] == "search" and len(r["results"]) == 2
