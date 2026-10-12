"""YouTube Data API v3: find a channel and read its latest videos with views, likes, comments and length.

Quota: about 3-5 units per channel per refresh (the free limit is 10,000 units a day).
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from config import YOUTUBE_API_KEY

API = "https://www.googleapis.com/youtube/v3/"
MAX_VIDEOS = 100  # latest videos read per channel


def _get(endpoint, **params):
    if not YOUTUBE_API_KEY:
        raise ValueError("YouTube API key is missing. Add YOUTUBE_API_KEY to backend\\.env")
    params["key"] = YOUTUBE_API_KEY
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=20) as res:
            return json.load(res)
    except urllib.error.HTTPError as exc:
        try:
            message = json.load(exc)["error"]["message"]
        except Exception:
            message = str(exc)
        raise ValueError(f"YouTube error: {message}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Can't reach YouTube: {exc.reason}") from exc


def _lookups(text):
    """Turn whatever the user pasted into a list of ways to find the channel, tried in order.

    Understands: @handle, handle, channel ID, and links like
      youtube.com/@handle(/videos), youtube.com/channel/UC..., youtube.com/user/name, youtube.com/c/name,
      youtube.com/watch?v=..., youtu.be/..., youtube.com/shorts/..., youtube.com/results?search_query=...
    Each item is ("channels", params), ("video", video_id) or ("search", query).
    """
    text = urllib.parse.unquote(text.strip())
    parsed = urllib.parse.urlparse(text if "://" in text else "https://" + text)
    host = parsed.netloc.lower()
    path = parsed.path
    query = urllib.parse.parse_qs(parsed.query)
    is_link = "youtube.com" in host or "youtu.be" in host

    if re.fullmatch(r"UC[\w-]{22}", text):
        return [("channels", {"id": text})]
    if not is_link:
        name = text.lstrip("@")
        if not re.fullmatch(r"[\w.\-]+", name):
            return [("search", text)]  # e.g. a channel name with spaces
        return [("channels", {"forHandle": "@" + name}), ("search", name)]

    if "youtu.be" in host and path.strip("/"):
        return [("video", path.strip("/").split("/")[0])]
    if "v" in query:
        return [("video", query["v"][0])]
    m = re.match(r"/(?:shorts|live|embed)/([\w-]{6,})", path)
    if m:
        return [("video", m.group(1))]
    m = re.match(r"/channel/(UC[\w-]{22})", path)
    if m:
        return [("channels", {"id": m.group(1)})]
    m = re.match(r"/@([\w.\-]+)", path)
    if m:
        return [("channels", {"forHandle": "@" + m.group(1)}), ("search", m.group(1))]
    m = re.match(r"/user/([\w.\-]+)", path)
    if m:
        return [("channels", {"forUsername": m.group(1)}), ("channels", {"forHandle": "@" + m.group(1)}), ("search", m.group(1))]
    m = re.match(r"/c/([\w.\-]+)", path)
    if m:
        return [("channels", {"forHandle": "@" + m.group(1)}), ("search", m.group(1))]
    if "search_query" in query:
        q = query["search_query"][0].strip()
        if re.fullmatch(r"@?[\w.\-]+", q):
            return [("channels", {"forHandle": "@" + q.lstrip("@")}), ("search", q)]
        return [("search", q)]
    raise ValueError("That YouTube link doesn't point to a channel. Open the channel page and copy its link, or type its handle like @mkbhd.")


def _channel_id_for(kind, value):
    """Return a channel ID for a video ID or a search, or None."""
    if kind == "video":
        data = _get("videos", part="snippet", id=value)
        items = data.get("items")
        return items[0]["snippet"]["channelId"] if items else None
    if kind == "search":  # costs 100 quota units, so it's only a fallback
        data = _get("search", part="snippet", type="channel", maxResults=1, q=value)
        items = data.get("items")
        return items[0]["snippet"]["channelId"] if items else None
    return None


def find_channel(text):
    data = {}
    for kind, value in _lookups(text):
        if kind == "channels":
            data = _get("channels", part="snippet,statistics,contentDetails", **value)
        else:
            channel_id = _channel_id_for(kind, value)
            if channel_id:
                data = _get("channels", part="snippet,statistics,contentDetails", id=channel_id)
        if data.get("items"):
            break
    if not data.get("items"):
        raise ValueError(f'YouTube channel "{text}" not found. Check the handle or link.')
    ch = data["items"][0]
    info = _channel_info(ch)
    info["uploads_playlist"] = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    return info


def _channel_info(ch):
    """Name, handle, logo and subscribers from one channels.list item."""
    stats = ch.get("statistics", {})
    thumbs = ch["snippet"].get("thumbnails", {})
    logo = (thumbs.get("default") or thumbs.get("medium") or {}).get("url")
    return {
        "channel_id": ch["id"],
        "title": ch["snippet"]["title"],
        "handle": ch["snippet"].get("customUrl"),
        "thumbnail": logo,
        "subscribers": None if stats.get("hiddenSubscriberCount") else int(stats.get("subscriberCount", 0)),
    }


# ---- Suggestions while typing ----

_suggest_cache = {}  # query -> (time, results); repeated searches cost nothing


def _squash(text):
    """'Prerna Malha' / '@prerna.malha' -> 'prernamalha', for loose name matching."""
    return re.sub(r"[^a-z0-9]", "", text.lower())
_CACHE_SECONDS = 6 * 3600


def suggest_channels(query, limit=8):
    """Channels matching what the user is typing: an exact handle match first (1 unit), then a search (100 units)."""
    q = query.strip().lstrip("@")
    if len(q) < 3:
        return []
    key = q.lower()
    cached = _suggest_cache.get(key)
    if cached and time.time() - cached[0] < _CACHE_SECONDS:
        return cached[1]

    exact_ids = []
    if re.fullmatch(r"[\w.\-]+", q):
        exact = _get("channels", part="id", forHandle="@" + q)
        exact_ids = [i["id"] for i in exact.get("items", [])]
    # A search costs 100 units whether it returns 1 or 10 results, so ask for 10.
    found = _get("search", part="snippet", type="channel", maxResults=10, q=q)
    ids = exact_ids + [i["snippet"]["channelId"] for i in found.get("items", []) if i["snippet"]["channelId"] not in exact_ids]

    results = []
    if ids:
        data = _get("channels", part="snippet,statistics", id=",".join(ids[:50]))
        by_id = {ch["id"]: _channel_info(ch) for ch in data.get("items", [])}
        typed = _squash(q)

        def rank(c):
            name_matches = typed in _squash(c["title"]) or typed in _squash(c["handle"] or "")
            return (not name_matches, -(c["subscribers"] or 0))

        # Exact handle first; then channels whose name/handle contains what was typed; then the biggest.
        others = sorted((by_id[i] for i in ids if i in by_id and i not in exact_ids), key=rank)
        results = ([by_id[i] for i in exact_ids if i in by_id] + others)[:limit]
    _suggest_cache[key] = (time.time(), results)
    return results


def parse_duration(iso):
    """'PT1H2M3S' -> 3723 seconds."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def latest_videos(uploads_playlist, max_videos=MAX_VIDEOS):
    ids, page = [], None
    while len(ids) < max_videos:
        params = {"part": "contentDetails", "playlistId": uploads_playlist, "maxResults": 50}
        if page:
            params["pageToken"] = page
        data = _get("playlistItems", **params)
        ids += [item["contentDetails"]["videoId"] for item in data.get("items", [])]
        page = data.get("nextPageToken")
        if not page:
            break
    ids = ids[:max_videos]

    videos = []
    for i in range(0, len(ids), 50):
        data = _get("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))
        for v in data.get("items", []):
            stats = v.get("statistics", {})
            videos.append({
                "title": v["snippet"]["title"].strip(),
                "link": f"https://www.youtube.com/watch?v={v['id']}",
                "published_at": datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00")),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats["likeCount"]) if "likeCount" in stats else None,
                "comments": int(stats["commentCount"]) if "commentCount" in stats else None,
                "duration_seconds": parse_duration(v["contentDetails"].get("duration")),
            })
    return videos
