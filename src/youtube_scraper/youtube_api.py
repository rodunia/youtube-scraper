from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class YouTubeAPIError(RuntimeError):
    """Base YouTube API error."""


class YouTubeQuotaExceededError(YouTubeAPIError):
    """Quota limit reached or quota-related API failure."""


@dataclass
class APIComment:
    comment_id: str
    raw_commenter_id: str
    raw_text: str
    like_count: int
    reply_count: int
    published_at: str
    language: str


BASE_URL = "https://www.googleapis.com/youtube/v3"
SHORT_MAX_DURATION_SEC = 60


class YouTubeAPIClient:
    def __init__(self, api_key: str, quota_limit: int = 10000, timeout_sec: int = 30) -> None:
        if not api_key:
            raise ValueError("YOUTUBE_API_KEY is required for live API extraction.")
        self.api_key = api_key
        self.quota_limit = quota_limit
        self.timeout_sec = timeout_sec
        self.units_used = 0

    def _request(self, endpoint: str, params: dict[str, str | int]) -> dict:
        query = dict(params)
        query["key"] = self.api_key
        url = f"{BASE_URL}/{endpoint}?{urllib.parse.urlencode(query)}"

        try:
            with urllib.request.urlopen(url, timeout=self.timeout_sec) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            self.units_used += 1
            body = exc.read().decode("utf-8", errors="ignore")
            reasons = _extract_error_reasons(body)
            if any(r in {"quotaExceeded", "dailyLimitExceeded"} for r in reasons):
                raise YouTubeQuotaExceededError(f"YouTube quota exceeded: {reasons}") from exc
            if any(r in {"commentsDisabled"} for r in reasons):
                raise YouTubeAPIError("commentsDisabled") from exc
            raise YouTubeAPIError(f"YouTube API HTTP error {exc.code}: {reasons or body[:200]}") from exc
        except urllib.error.URLError as exc:
            raise YouTubeAPIError(f"Network error calling YouTube API: {exc}") from exc

        self.units_used += 1
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise YouTubeAPIError("Invalid JSON response from YouTube API") from exc

    def _list_uploads_playlist_id(self, channel_id: str) -> str:
        data = self._request(
            "channels",
            {
                "part": "contentDetails",
                "id": channel_id,
                "maxResults": 1,
            },
        )
        items = data.get("items", [])
        if not items:
            raise YouTubeAPIError(f"Channel not found: {channel_id}")
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    def resolve_channel_id(self, channel_reference: str, channel_name: str = "") -> str:
        ref = (channel_reference or "").strip()
        name = (channel_name or "").strip()

        if ref.startswith("UC"):
            return ref

        if "youtube.com/" in ref:
            parsed = urllib.parse.urlparse(ref)
            path_parts = [p for p in parsed.path.split("/") if p]
            if path_parts:
                if path_parts[0] == "channel" and len(path_parts) > 1 and path_parts[1].startswith("UC"):
                    return path_parts[1]
                if path_parts[0].startswith("@"):
                    resolved = self._resolve_by_handle(path_parts[0][1:])
                    if resolved:
                        return resolved

        if ref.startswith("@"):
            resolved = self._resolve_by_handle(ref[1:])
            if resolved:
                return resolved

        if ref:
            resolved = self._resolve_by_username(ref)
            if resolved:
                return resolved
            resolved = self._search_channel_id(ref)
            if resolved:
                return resolved

        if name:
            resolved = self._search_channel_id(name)
            if resolved:
                return resolved

        raise YouTubeAPIError(f"Unable to resolve channel identifier for ref='{ref}' name='{name}'")

    def _resolve_by_handle(self, handle: str) -> str | None:
        if not handle:
            return None
        data = self._request(
            "channels",
            {
                "part": "id",
                "forHandle": handle,
                "maxResults": 1,
            },
        )
        items = data.get("items", [])
        if items:
            cid = items[0].get("id")
            if cid:
                return str(cid)
        return None

    def _resolve_by_username(self, username: str) -> str | None:
        if not username:
            return None
        data = self._request(
            "channels",
            {
                "part": "id",
                "forUsername": username,
                "maxResults": 1,
            },
        )
        items = data.get("items", [])
        if items:
            cid = items[0].get("id")
            if cid:
                return str(cid)
        return None

    def _search_channel_id(self, query: str) -> str | None:
        if not query:
            return None
        data = self._request(
            "search",
            {
                "part": "snippet",
                "q": query,
                "type": "channel",
                "maxResults": 1,
            },
        )
        items = data.get("items", [])
        if not items:
            return None
        channel_id = items[0].get("snippet", {}).get("channelId")
        return str(channel_id) if channel_id else None

    def list_recent_upload_video_ids(self, channel_id: str, limit: int = 80) -> list[str]:
        uploads_playlist = self._list_uploads_playlist_id(channel_id)

        video_ids: list[str] = []
        page_token: str | None = None

        while len(video_ids) < limit:
            data = self._request(
                "playlistItems",
                {
                    "part": "contentDetails",
                    "playlistId": uploads_playlist,
                    "maxResults": 50,
                    **({"pageToken": page_token} if page_token else {}),
                },
            )
            items = data.get("items", [])
            if not items:
                break
            for item in items:
                v_id = item.get("contentDetails", {}).get("videoId")
                if v_id:
                    video_ids.append(v_id)
                if len(video_ids) >= limit:
                    break
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return video_ids[:limit]

    def get_video_metadata(self, video_ids: list[str]) -> dict[str, dict]:
        metadata: dict[str, dict] = {}
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i : i + 50]
            if not chunk:
                continue
            data = self._request(
                "videos",
                {
                    "part": "snippet,statistics,contentDetails",
                    "id": ",".join(chunk),
                    "maxResults": len(chunk),
                },
            )
            for item in data.get("items", []):
                v_id = item.get("id")
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                content_details = item.get("contentDetails", {})
                if not v_id:
                    continue
                duration_seconds = _parse_iso8601_duration_to_seconds(
                    str(content_details.get("duration") or "")
                )
                metadata[v_id] = {
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "view_count": _safe_int(stats.get("viewCount")),
                    "duration_seconds": duration_seconds,
                    "is_short": bool(
                        duration_seconds is not None and 0 < duration_seconds <= SHORT_MAX_DURATION_SEC
                    ),
                }
        return metadata

    def get_top_level_comments(
        self,
        *,
        video_id: str,
        scan_limit: int = 200,
    ) -> tuple[list[APIComment], str]:
        comments: list[APIComment] = []
        page_token: str | None = None
        fetched = 0

        while fetched < scan_limit:
            page_size = min(100, scan_limit - fetched)
            try:
                data = self._request(
                    "commentThreads",
                    {
                        "part": "snippet",
                        "videoId": video_id,
                        "maxResults": page_size,
                        "order": "relevance",
                        "textFormat": "plainText",
                        **({"pageToken": page_token} if page_token else {}),
                    },
                )
            except YouTubeAPIError as exc:
                msg = str(exc)
                if "commentsDisabled" in msg:
                    return [], "comments_disabled"
                raise

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                top = item.get("snippet", {}).get("topLevelComment", {})
                top_snippet = top.get("snippet", {})
                commenter = top_snippet.get("authorChannelId", {}).get("value") or top_snippet.get(
                    "authorDisplayName", "unknown"
                )

                comments.append(
                    APIComment(
                        comment_id=top.get("id", ""),
                        raw_commenter_id=str(commenter),
                        raw_text=top_snippet.get("textDisplay")
                        or top_snippet.get("textOriginal")
                        or "",
                        like_count=int(top_snippet.get("likeCount", 0) or 0),
                        reply_count=int(item.get("snippet", {}).get("totalReplyCount", 0) or 0),
                        published_at=top_snippet.get("publishedAt", ""),
                        language="",
                    )
                )

            fetched += len(items)
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return comments, "ok"


def _extract_error_reasons(error_body: str) -> list[str]:
    try:
        data = json.loads(error_body)
    except json.JSONDecodeError:
        return []

    reasons: list[str] = []
    for err in data.get("error", {}).get("errors", []):
        reason = err.get("reason")
        if reason:
            reasons.append(str(reason))
    return reasons


def _safe_int(value: object) -> int | None:
    try:
        return int(str(value))
    except Exception:
        return None


def _parse_iso8601_duration_to_seconds(value: str) -> int | None:
    if not value or not value.startswith("P"):
        return None
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
        value,
    )
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds
