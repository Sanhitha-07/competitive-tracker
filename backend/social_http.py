"""HTTP for the Instagram, Facebook and X APIs: one place for retries and error meanings.

  TokenInvalid   the token expired or was revoked: the user must reconnect (never retried)
  NotPermitted   the app lacks a permission / API access level for this data (never retried)
  RateLimited    the platform's limit was hit: stop this platform until the next Refresh
  ApiError       anything else; temporary failures (5xx, timeouts) are retried a few times first

Tests replace `transport` with a fake, so no real request is ever made in tests.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

RETRIES = 2            # extra attempts for temporary failures
BACKOFF_SECONDS = 1.5  # wait 1.5s, then 3s


class ApiError(ValueError):
    pass


class TokenInvalid(ApiError):
    pass


class NotPermitted(ApiError):
    pass


class RateLimited(ApiError):
    pass


def _urllib_transport(method, url, headers, body, timeout):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read().decode("utf-8", "replace"), dict(res.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), dict(exc.headers or {})


transport = _urllib_transport  # (method, url, headers, body, timeout) -> (status, text, headers)


def request(method, url, *, params=None, data=None, headers=None, classify, timeout=20, sleep=time.sleep):
    """Send a request and return parsed JSON. `classify(status, body)` maps a platform's error to one
    of the exceptions above (or None for a plain ApiError)."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    hdrs = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    for attempt in range(RETRIES + 1):
        try:
            status, text, _ = transport(method, url, hdrs, body, timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < RETRIES:
                sleep(BACKOFF_SECONDS * (attempt + 1))
                continue
            raise ApiError(f"Can't reach the platform: {getattr(exc, 'reason', exc)}") from None
        try:
            parsed = json.loads(text) if text else {}
        except ValueError:
            parsed = {"raw": text[:300]}
        if 200 <= status < 300:
            return parsed
        err = classify(status, parsed)
        if isinstance(err, (TokenInvalid, NotPermitted, RateLimited)):
            raise err
        if status >= 500 and attempt < RETRIES:
            sleep(BACKOFF_SECONDS * (attempt + 1))
            continue
        raise err or ApiError(f"The platform returned an error ({status}).")
    raise ApiError("The platform didn't respond.")
