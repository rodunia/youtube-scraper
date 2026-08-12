from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


class YtDlpExtractorError(RuntimeError):
    """yt-dlp extraction failed."""


@dataclass
class YtDlpComment:
    comment_id: str
    raw_commenter_id: str
    raw_text: str
    like_count: int
    reply_count: int
    published_at: str
    language: str


class YtDlpExtractor:
    def _import_yt_dlp(self):
        try:
            from yt_dlp import YoutubeDL
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise YtDlpExtractorError(
                "yt-dlp is not available. Install dependency `yt-dlp` first."
            ) from exc
        return YoutubeDL

    def list_recent_video_ids(
        self,
        *,
        channel_url: str,
        limit: int = 20,
        content_type: str = "videos",
    ) -> list[str]:
        YoutubeDL = self._import_yt_dlp()

        if content_type not in {"videos", "shorts"}:
            raise ValueError(f"Unsupported content_type={content_type}. Expected 'videos' or 'shorts'.")

        url = channel_url.rstrip("/")
        if url.endswith("/videos") or url.endswith("/shorts"):
            url = url.rsplit("/", 1)[0]
        url = f"{url}/{content_type}"

        opts = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": True,
            "playlistend": int(limit),
            "ignoreerrors": True,
            "nocheckcertificate": True,
        }

        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            raise YtDlpExtractorError(f"yt-dlp channel extraction failed for {channel_url}: {exc}") from exc

        entries = (info or {}).get("entries") or []
        video_ids: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            if not entry:
                continue
            vid = str(entry.get("id") or "").strip()
            if not vid or vid in seen:
                continue
            seen.add(vid)
            video_ids.append(vid)
            if len(video_ids) >= limit:
                break

        return video_ids

    def get_top_level_comments(self, *, video_url: str, limit: int = 20) -> tuple[list[YtDlpComment], str]:
        YoutubeDL = self._import_yt_dlp()

        opts = {
            "quiet": True,
            "skip_download": True,
            "getcomments": True,
            "ignoreerrors": True,
            "nocheckcertificate": True,
        }

        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
        except Exception as exc:
            raise YtDlpExtractorError(f"yt-dlp video extraction failed for {video_url}: {exc}") from exc

        if not info:
            return [], "ok"

        comments_raw = info.get("comments") or []
        if not isinstance(comments_raw, list):
            comments_raw = []

        top_level: list[dict] = []
        for c in comments_raw:
            if not isinstance(c, dict):
                continue
            parent = c.get("parent")
            if parent in (None, "root", ""):
                top_level.append(c)

        parsed: list[YtDlpComment] = []
        for idx, c in enumerate(top_level):
            text = str(c.get("text") or "").strip()
            if not text:
                continue

            timestamp = c.get("timestamp")
            if isinstance(timestamp, (int, float)) and timestamp > 0:
                published_at = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            else:
                published_at = ""

            parsed.append(
                YtDlpComment(
                    comment_id=str(c.get("id") or f"ytdlp_{idx}"),
                    raw_commenter_id=str(c.get("author_id") or c.get("author") or "unknown"),
                    raw_text=text,
                    like_count=int(c.get("like_count") or 0),
                    reply_count=self._parse_reply_count(c.get("replies")),
                    published_at=published_at,
                    language="",
                )
            )

        # Keep ranking consistent with project policy: top-by-likes, older timestamp tie-break.
        parsed.sort(key=lambda x: (-int(x.like_count or 0), x.published_at or "9999-12-31T23:59:59+00:00"))
        selected = parsed[:limit]

        status = "ok" if len(selected) >= limit else "not_enough_comments"
        return selected, status

    @staticmethod
    def _parse_reply_count(value: object) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            nested = value.get("total")
            if isinstance(nested, (int, float)):
                return int(nested)
            return 0
        try:
            return int(str(value or 0))
        except Exception:
            return 0
