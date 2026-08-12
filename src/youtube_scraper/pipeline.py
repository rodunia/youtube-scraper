from __future__ import annotations

import csv
import hashlib
import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from .config import AppConfig
from .db import (
    create_run,
    finalize_run,
    insert_comment,
    insert_qa_report,
    insert_video,
    upsert_channel,
)
from .playwright_extractor import PlaywrightCommentExtractor, PlaywrightExtractorError
from .preprocessing import ProcessedComment, process_comment
from .qa import build_run_qa_report
from .youtube_api import YouTubeAPIClient, YouTubeQuotaExceededError
from .ytdlp_extractor import YtDlpExtractor

MAX_CHANNELS = 300
MAX_VIDEOS = 24000
MAX_COMMENTS = 480000
COMMENTS_PER_VIDEO = 20
COMMENT_SCAN_LIMIT = 200
DEFAULT_MAX_RECENT_VIDEOS_PER_CHANNEL = 80
DEFAULT_MIN_EXPECTED_VIDEOS_PER_CHANNEL = 30
DEFAULT_CONTENT_TYPE = "videos"
RETRY_BACKOFF_SEC = (5, 15, 60)
DISCOVERY_OVERSAMPLE_FACTOR = 4
DISCOVERY_HARD_CAP = 400


@dataclass
class TargetChannel:
    channel_identifier: str
    channel_name: str
    channel_url: str
    channel_niche: str


class CommentLike(Protocol):
    comment_id: str
    raw_commenter_id: str
    raw_text: str
    like_count: int
    reply_count: int
    published_at: str
    language: str


@dataclass
class SimulatedComment:
    comment_id: str
    raw_commenter_id: str
    raw_text: str
    like_count: int
    reply_count: int
    published_at: str
    language: str


class APIClientPool:
    def __init__(self, api_keys: list[str], quota_limit: int) -> None:
        self.quota_limit = quota_limit
        self.clients = [YouTubeAPIClient(key, quota_limit=quota_limit) for key in api_keys if key.strip()]
        self.available = [True for _ in self.clients]
        self.idx = 0

    @property
    def total_units_used(self) -> int:
        return sum(c.units_used for c in self.clients)

    @property
    def total_quota_limit(self) -> int:
        return self.quota_limit * max(len(self.clients), 1)

    def has_available(self) -> bool:
        return any(self.available)

    def _seek_available(self) -> None:
        if not self.clients:
            return
        for _ in range(len(self.clients)):
            if self.available[self.idx]:
                return
            self.idx = (self.idx + 1) % len(self.clients)

    def call(self, fn):
        if not self.clients:
            raise YouTubeQuotaExceededError("No API keys configured")

        attempted = 0
        while attempted < len(self.clients):
            if not self.has_available():
                raise YouTubeQuotaExceededError("All API keys exceeded quota")
            self._seek_available()
            client = self.clients[self.idx]
            try:
                return fn(client)
            except YouTubeQuotaExceededError:
                self.available[self.idx] = False
                attempted += 1
                self.idx = (self.idx + 1) % len(self.clients)
                continue
        raise YouTubeQuotaExceededError("All API keys exceeded quota")


def load_targets_csv(path: Path) -> list[TargetChannel]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = set(reader.fieldnames or [])
        rows: list[TargetChannel] = []

        if {"channel_id", "channel_url", "channel_niche"}.issubset(fields):
            for row in reader:
                ident = (row.get("channel_id") or "").strip()
                channel_name = (row.get("channel_name") or "").strip()
                rows.append(
                    TargetChannel(
                        channel_identifier=ident,
                        channel_name=channel_name,
                        channel_url=(row.get("channel_url") or "").strip(),
                        channel_niche=(row.get("channel_niche") or "").strip(),
                    )
                )
        elif {"channel_identifier", "channel_name", "niche"}.issubset(fields):
            for row in reader:
                ident = (row.get("channel_identifier") or "").strip()
                channel_name = (row.get("channel_name") or "").strip()
                rows.append(
                    TargetChannel(
                        channel_identifier=ident,
                        channel_name=channel_name,
                        channel_url=_derive_channel_url(ident, channel_name),
                        channel_niche=(row.get("niche") or "").strip(),
                    )
                )
        else:
            raise ValueError(
                "Targets CSV must include either "
                "['channel_id','channel_url','channel_niche'] or "
                "['channel_identifier','channel_name','niche']"
            )

    return [row for row in rows if row.channel_identifier or row.channel_name]


def _derive_channel_url(identifier: str, channel_name: str) -> str:
    if identifier.startswith("http://") or identifier.startswith("https://"):
        return identifier
    if identifier.startswith("@"):
        return f"https://www.youtube.com/{identifier}"
    if identifier.startswith("UC"):
        return f"https://www.youtube.com/channel/{identifier}"
    if channel_name:
        return f"https://www.youtube.com/results?search_query={channel_name.replace(' ', '+')}"
    return ""


def _resolve_fallback_channel_url(
    pw: PlaywrightCommentExtractor,
    target: TargetChannel,
) -> str:
    channel_url = target.channel_url or _derive_channel_url(target.channel_identifier, target.channel_name)
    if "/results?" not in channel_url:
        return channel_url
    if not target.channel_name:
        return ""
    try:
        return pw.resolve_channel_url(query=target.channel_name) or ""
    except Exception:
        return ""


def _fallback_channel_key(target: TargetChannel) -> str:
    seed = f"{target.channel_identifier}|{target.channel_name}|{target.channel_url}"
    return "UNRESOLVED_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _best_channel_key(target: TargetChannel) -> str:
    return target.channel_identifier or target.channel_name or _fallback_channel_key(target)


def _mock_comment_text(i: int) -> str:
    spam_samples = [
        "subscribe back subscribe back subscribe back",
        "Check my channel for free crypto signals https://a.co https://b.co",
        "free giveaway click my bio now now now",
    ]
    if i % 23 == 0:
        return spam_samples[(i // 23) % len(spam_samples)]

    skepticism_openers = [
        "This looks staged to me",
        "Something feels off here",
        "The motion looks unnatural",
        "The face details seem inconsistent",
        "This edit feels synthetic",
    ]
    proof_requests = [
        "can you show BTS footage",
        "could you post the raw clip",
        "can we see an unedited version",
        "could you share project files",
        "can you show the original take",
    ]
    neutral_reactions = [
        "Interesting upload",
        "The idea is clever",
        "The pacing works well",
        "I like the concept",
        "Pretty strong hook",
    ]
    normalization_lines = [
        "even if AI helped, the result is still entertaining",
        "using AI tools does not bother me here",
        "people are overreacting if this used AI",
        "I only care whether the final video works",
        "AI or not, the storytelling is what matters",
    ]
    specifics = [
        "around the hand movement",
        "in the eye reflections",
        "near the voice transition",
        "during the background change",
        "in the lighting on the face",
        "at the cut near the end",
        "when the camera moves in",
        "in the mouth sync",
    ]
    markers = [
        "frame",
        "moment",
        "section",
        "beat",
        "cut",
        "timestamp",
    ]

    mod = i % 4
    marker = markers[(i // 3) % len(markers)]
    marker_value = (i % 37) + 3
    detail = specifics[(i // 5) % len(specifics)]

    if mod == 0:
        return (
            f"{skepticism_openers[(i // 2) % len(skepticism_openers)]} {detail}; "
            f"{proof_requests[(i // 7) % len(proof_requests)]} for {marker} {marker_value}?"
        )
    if mod == 1:
        return (
            f"{neutral_reactions[(i // 2) % len(neutral_reactions)]}. "
            f"I noticed {detail} at {marker} {marker_value}."
        )
    if mod == 2:
        return (
            f"{normalization_lines[(i // 2) % len(normalization_lines)]}. "
            f"The detail {detail} did not ruin it for me at {marker} {marker_value}."
        )
    return (
        f"This was probably made with AI {detail}, but "
        f"{proof_requests[(i // 11) % len(proof_requests)]} before people argue about {marker} {marker_value}."
    )


def _select_engine(config: AppConfig, api_units_used: int, api_quota_limit: int | None = None) -> str:
    if config.execution_mode == "api_only":
        return "api"
    if config.execution_mode == "playwright_only":
        return "playwright"
    effective_quota = api_quota_limit if api_quota_limit is not None else config.api_daily_quota
    quota_ratio = api_units_used / max(effective_quota, 1)
    return "playwright" if quota_ratio >= config.api_failover_threshold else "api"


def _sort_top_comments(comments: list[CommentLike]) -> list[CommentLike]:
    # Tiebreak policy: same like_count -> older timestamp first.
    return sorted(
        comments,
        key=lambda c: (
            -int(c.like_count or 0),
            c.published_at or "9999-12-31T23:59:59Z",
        ),
    )


def _retry_api_call(func, *, context: str):
    last_exc: Exception | None = None
    for attempt, wait_sec in enumerate(RETRY_BACKOFF_SEC, start=1):
        try:
            return func()
        except YouTubeQuotaExceededError:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt == len(RETRY_BACKOFF_SEC):
                break
            time.sleep(wait_sec)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"API retry failure without exception in {context}")


def _retry_playwright_call(func, *, context: str):
    last_exc: Exception | None = None
    for attempt, wait_sec in enumerate(RETRY_BACKOFF_SEC, start=1):
        try:
            return func()
        except Exception as exc:
            last_exc = exc
            if attempt == len(RETRY_BACKOFF_SEC):
                break
            time.sleep(wait_sec)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Playwright retry failure without exception in {context}")


def _discovery_limit(videos_per_channel: int) -> int:
    return max(videos_per_channel, min(DISCOVERY_HARD_CAP, videos_per_channel * DISCOVERY_OVERSAMPLE_FACTOR))


def _video_matches_content_type(meta: dict, content_type: str) -> bool:
    is_short = bool(meta.get("is_short"))
    if content_type == "shorts":
        return is_short
    if content_type == "videos":
        return not is_short
    raise ValueError(f"Unsupported content_type={content_type}. Expected 'videos' or 'shorts'.")


def _select_clean_top_comments(
    *,
    ranked_comments: list[CommentLike],
    config: AppConfig,
    template_threshold: float,
    spam_blacklist: set[str],
    global_normalized_counts: dict[str, int],
    global_normalized_samples: list[str],
) -> list[tuple[CommentLike, ProcessedComment]]:
    selected: list[tuple[CommentLike, ProcessedComment]] = []
    video_normalized_seen: set[str] = set()

    for comment in ranked_comments:
        processed = process_comment(
            raw_commenter_id=comment.raw_commenter_id,
            raw_text=comment.raw_text,
            secret_salt=config.hash_salt,
            previous_video_normalized=video_normalized_seen,
            global_normalized_counts=global_normalized_counts,
            global_normalized_samples=global_normalized_samples,
            template_threshold=template_threshold,
            spam_blacklist=spam_blacklist,
        )

        normalized = " ".join(processed.cleaned_text.lower().split())
        video_normalized_seen.add(normalized)
        global_normalized_counts[normalized] = global_normalized_counts.get(normalized, 0) + 1
        global_normalized_samples.append(normalized)

        if processed.is_spam or processed.is_template or processed.is_duplicate:
            continue

        selected.append((comment, processed))
        if len(selected) >= COMMENTS_PER_VIDEO:
            break

    return selected


def _run_simulated(
    conn: sqlite3.Connection,
    config: AppConfig,
    targets: list[TargetChannel],
    *,
    template_threshold: float,
    run_id: int,
) -> tuple[bool, int, int, int, dict[str, object]]:
    api_units_used = 0
    api_comment_count = 0
    playwright_comment_count = 0
    run_truncated = False
    runtime_niche: dict[str, dict[str, int]] = {}

    global_normalized_counts: dict[str, int] = {}
    global_normalized_samples: list[str] = []
    spam_blacklist: set[str] = {"free bitcoin giveaway click now"}

    channel_counter = 0
    video_counter = 0
    comment_counter = 0

    for target in targets:
        niche = target.channel_niche or "unknown"
        niche_stats = runtime_niche.setdefault(
            niche,
            {
                "requested_channels": 0,
                "collected_channels": 0,
                "coverage_shortfall_channels": 0,
                "no_shorts_available_channels": 0,
                "extraction_failed_channels": 0,
            },
        )
        niche_stats["requested_channels"] += 1
        if channel_counter >= MAX_CHANNELS:
            run_truncated = True
            break

        channel_key = _best_channel_key(target)
        channel_db_id = upsert_channel(
            conn,
            channel_id=channel_key,
            channel_url=target.channel_url,
            niche=target.channel_niche,
            coverage_shortfall=True,
            no_shorts_available=False,
            extraction_failed=False,
        )
        channel_counter += 1
        niche_stats["collected_channels"] += 1

        for v_idx in range(2):
            if video_counter >= MAX_VIDEOS or comment_counter >= MAX_COMMENTS:
                run_truncated = True
                break

            video_id = f"{channel_key}_video_{v_idx+1}"
            now = datetime.now(tz=timezone.utc)
            published_at = (now - timedelta(days=v_idx * 3)).isoformat()

            source_engine = _select_engine(config, api_units_used)

            simulated_candidates: list[CommentLike] = []
            for c_idx in range(COMMENT_SCAN_LIMIT):
                if comment_counter >= MAX_COMMENTS:
                    run_truncated = True
                    break

                text = _mock_comment_text(c_idx)
                simulated_candidates.append(
                    SimulatedComment(
                        comment_id=f"{video_id}_comment_{c_idx+1}",
                        raw_commenter_id=f"user_{channel_key}_{v_idx}_{c_idx % 7}",
                        raw_text=text,
                        like_count=max(0, 1000 - c_idx),
                        reply_count=random.randint(0, 20),
                        published_at=published_at,
                        language="en",
                    )
                )

            selected_clean = _select_clean_top_comments(
                ranked_comments=_sort_top_comments(simulated_candidates),
                config=config,
                template_threshold=template_threshold,
                spam_blacklist=spam_blacklist,
                global_normalized_counts=global_normalized_counts,
                global_normalized_samples=global_normalized_samples,
            )
            simulated_status = "ok" if len(selected_clean) >= COMMENTS_PER_VIDEO else "not_enough_comments"

            video_db_id = insert_video(
                conn,
                run_id=run_id,
                channel_db_id=channel_db_id,
                video_id=video_id,
                video_url=f"https://youtube.com/watch?v={video_id}",
                title=f"Mock video {v_idx+1}",
                description="Simulated extraction placeholder.",
                published_at=published_at,
                upload_index=v_idx + 1,
                comment_status=simulated_status,
                view_count=random.randint(1000, 100000),
                disclosure_quality=random.choice([0, 1, 2, 3]),
                collection_engine="api" if source_engine == "api" else "playwright",
                comments_scanned=len(simulated_candidates),
                comments_saved=len(selected_clean),
                comments_filtered=max(0, len(simulated_candidates) - len(selected_clean)),
                failure_reason="not_enough_clean_comments" if simulated_status != "ok" else None,
                extraction_failed=False,
            )
            video_counter += 1

            for rank, (comment, processed) in enumerate(selected_clean, start=1):
                insert_comment(
                    conn,
                    run_id=run_id,
                    channel_db_id=channel_db_id,
                    video_db_id=video_db_id,
                    comment_id=comment.comment_id,
                    commenter_hash_id=processed.commenter_hash_id,
                    raw_text=processed.raw_text,
                    cleaned_text=processed.cleaned_text,
                    like_count=int(comment.like_count or 0),
                    reply_count=int(comment.reply_count or 0),
                    published_at=comment.published_at,
                    language=comment.language,
                    comment_rank=rank,
                    is_spam=processed.is_spam,
                    is_template=processed.is_template,
                    is_duplicate=processed.is_duplicate,
                    spam_rule_hits=processed.spam_rule_hits,
                    source_engine=source_engine,
                )
                comment_counter += 1

            if source_engine == "api":
                api_units_used += 1
                api_comment_count += len(selected_clean)
            else:
                playwright_comment_count += len(selected_clean)

            if run_truncated:
                break

        if run_truncated:
            break

    return (
        run_truncated,
        api_units_used,
        api_comment_count,
        playwright_comment_count,
        {
            "channels_requested": len(targets),
            "coverage_shortfall_channels": 0,
            "no_shorts_available_channels": 0,
            "extraction_failed_channels": 0,
            "niche_attrition": runtime_niche,
        },
    )


def _run_live(
    conn: sqlite3.Connection,
    config: AppConfig,
    targets: list[TargetChannel],
    *,
    template_threshold: float,
    run_id: int,
    videos_per_channel: int,
    min_expected_videos_per_channel: int,
    content_type: str,
) -> tuple[bool, int, int, int, dict[str, object]]:
    if not config.hash_salt:
        raise ValueError("HASH_SALT is required for live extraction mode.")
    if config.execution_mode != "playwright_only" and not config.youtube_api_keys:
        raise ValueError("At least one API key is required unless EXECUTION_MODE=playwright_only.")

    api_pool = APIClientPool(config.youtube_api_keys, quota_limit=config.api_daily_quota)
    pw = PlaywrightCommentExtractor(headless=True)
    ytdlp = YtDlpExtractor()
    api_blocked = config.execution_mode == "playwright_only" or not api_pool.clients

    run_truncated = False
    api_comment_count = 0
    playwright_comment_count = 0

    global_normalized_counts: dict[str, int] = {}
    global_normalized_samples: list[str] = []
    spam_blacklist: set[str] = {"free bitcoin giveaway click now"}

    channel_counter = 0
    video_counter = 0
    comment_counter = 0
    coverage_shortfall_channels = 0
    no_shorts_available_channels = 0
    extraction_failed_channels = 0
    runtime_niche: dict[str, dict[str, int]] = {}

    for target in targets:
        niche = target.channel_niche or "unknown"
        niche_stats = runtime_niche.setdefault(
            niche,
            {
                "requested_channels": 0,
                "collected_channels": 0,
                "coverage_shortfall_channels": 0,
                "no_shorts_available_channels": 0,
                "extraction_failed_channels": 0,
            },
        )
        niche_stats["requested_channels"] += 1
        if channel_counter >= MAX_CHANNELS:
            run_truncated = True
            break

        ref = target.channel_identifier or target.channel_name
        if not ref:
            coverage_shortfall_channels += 1
            extraction_failed_channels += 1
            niche_stats["coverage_shortfall_channels"] += 1
            niche_stats["extraction_failed_channels"] += 1
            upsert_channel(
                conn,
                channel_id=_fallback_channel_key(target),
                channel_url=target.channel_url,
                niche=target.channel_niche,
                coverage_shortfall=True,
                no_shorts_available=False,
                extraction_failed=True,
            )
            channel_counter += 1
            continue

        resolved_channel_id: str | None = None
        video_ids: list[str] = []
        video_metadata: dict[str, dict] = {}
        no_shorts_available = False

        if not api_blocked and config.execution_mode != "playwright_only":
            try:
                resolved_channel_id = _retry_api_call(
                    lambda: api_pool.call(lambda c: c.resolve_channel_id(ref, target.channel_name)),
                    context=f"resolve_channel_id({ref})",
                )
                candidate_video_ids = _retry_api_call(
                    lambda: api_pool.call(
                        lambda c: c.list_recent_upload_video_ids(
                            resolved_channel_id, limit=_discovery_limit(videos_per_channel)
                        )
                    ),
                    context=f"list_recent_upload_video_ids({resolved_channel_id})",
                )
                if candidate_video_ids:
                    candidate_metadata = _retry_api_call(
                        lambda: api_pool.call(lambda c: c.get_video_metadata(candidate_video_ids)),
                        context=f"filter_content_type_metadata({resolved_channel_id})",
                    )
                    filtered_video_ids = [
                        video_id
                        for video_id in candidate_video_ids
                        if video_id in candidate_metadata
                        and _video_matches_content_type(candidate_metadata[video_id], content_type)
                    ]
                    video_ids = filtered_video_ids[:videos_per_channel]
                    video_metadata = {
                        video_id: candidate_metadata[video_id]
                        for video_id in video_ids
                        if video_id in candidate_metadata
                    }
                    if content_type == "shorts" and not video_ids:
                        no_shorts_available = True
            except YouTubeQuotaExceededError:
                api_blocked = True
            except Exception:
                # Continue to Playwright discovery fallback.
                pass

        if not video_ids and config.execution_mode != "api_only":
            channel_url = _resolve_fallback_channel_url(pw, target)
            try:
                if channel_url:
                    video_ids = _retry_playwright_call(
                        lambda: ytdlp.list_recent_video_ids(
                            channel_url=channel_url,
                            limit=videos_per_channel,
                            content_type=content_type,
                        ),
                        context=f"ytdlp_video_discovery({channel_url})",
                    )
            except Exception as exc:
                if content_type == "shorts" and "does not have a shorts tab" in str(exc).lower():
                    no_shorts_available = True
                video_ids = []

        if not video_ids and config.execution_mode != "api_only":
            channel_url = _resolve_fallback_channel_url(pw, target)
            try:
                if channel_url:
                    video_ids = _retry_playwright_call(
                        lambda: pw.list_recent_video_ids(
                            channel_url=channel_url,
                            limit=videos_per_channel,
                            content_type=content_type,
                        ),
                        context=f"playwright_video_discovery({channel_url})",
                    )
            except Exception as exc:
                if content_type == "shorts" and "does not have a shorts tab" in str(exc).lower():
                    no_shorts_available = True
                video_ids = []

        if not video_ids:
            extraction_failed = not no_shorts_available
            coverage_shortfall_channels += 1
            niche_stats["coverage_shortfall_channels"] += 1
            if no_shorts_available:
                no_shorts_available_channels += 1
                niche_stats["no_shorts_available_channels"] += 1
            if extraction_failed:
                extraction_failed_channels += 1
                niche_stats["extraction_failed_channels"] += 1
            upsert_channel(
                conn,
                channel_id=resolved_channel_id or _fallback_channel_key(target),
                channel_url=target.channel_url,
                niche=target.channel_niche,
                coverage_shortfall=True,
                no_shorts_available=no_shorts_available,
                extraction_failed=extraction_failed,
            )
            channel_counter += 1
            continue

        coverage_shortfall = len(video_ids) < min_expected_videos_per_channel
        if coverage_shortfall:
            coverage_shortfall_channels += 1
            niche_stats["coverage_shortfall_channels"] += 1
        channel_key = resolved_channel_id or _best_channel_key(target)
        channel_db_id = upsert_channel(
            conn,
            channel_id=channel_key,
            channel_url=target.channel_url
            or (f"https://www.youtube.com/channel/{resolved_channel_id}" if resolved_channel_id else ""),
            niche=target.channel_niche,
            coverage_shortfall=coverage_shortfall,
            no_shorts_available=False,
            extraction_failed=False,
        )
        channel_counter += 1
        niche_stats["collected_channels"] += 1

        if (
            video_ids
            and resolved_channel_id
            and not api_blocked
            and config.execution_mode != "playwright_only"
        ):
            try:
                missing_video_ids = [video_id for video_id in video_ids if video_id not in video_metadata]
                if missing_video_ids:
                    fetched_metadata = _retry_api_call(
                        lambda: api_pool.call(lambda c: c.get_video_metadata(missing_video_ids)),
                        context=f"get_video_metadata({resolved_channel_id})",
                    )
                    video_metadata.update(fetched_metadata)
            except YouTubeQuotaExceededError:
                api_blocked = True
            except Exception:
                pass

        for upload_index, video_id in enumerate(video_ids, start=1):
            if video_counter >= MAX_VIDEOS or comment_counter >= MAX_COMMENTS:
                run_truncated = True
                break

            meta = video_metadata.get(video_id, {})
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            if config.execution_mode == "playwright_only" or api_blocked:
                source_engine = "playwright"
            else:
                source_engine = _select_engine(
                    config,
                    api_pool.total_units_used,
                    api_pool.total_quota_limit,
                )
            extracted: list[CommentLike] = []
            collection_engine: str | None = None
            comment_status = "ok"
            extraction_failed = False
            failure_reason: str | None = None

            if source_engine == "api":
                try:
                    collection_engine = "api"
                    extracted, comment_status = _retry_api_call(
                        lambda: api_pool.call(
                            lambda c: c.get_top_level_comments(
                                video_id=video_id, scan_limit=COMMENT_SCAN_LIMIT
                            )
                        ),
                        context=f"api_comments({video_id})",
                    )
                except YouTubeQuotaExceededError:
                    api_blocked = True
                    if config.execution_mode == "auto":
                        source_engine = "playwright"
                        collection_engine = None
                    else:
                        extraction_failed = True
                        comment_status = "extraction_failed"
                        failure_reason = "api_quota_exceeded"
                except Exception:
                    if config.execution_mode == "auto":
                        source_engine = "playwright"
                        collection_engine = None
                        extracted = []
                        comment_status = "ok"
                    else:
                        extraction_failed = True
                        comment_status = "extraction_failed"
                        failure_reason = "api_comment_extraction_failed"

            if source_engine == "playwright" and not extraction_failed:
                try:
                    collection_engine = "ytdlp"
                    extracted, comment_status = _retry_playwright_call(
                        lambda: ytdlp.get_top_level_comments(
                            video_url=video_url, limit=COMMENT_SCAN_LIMIT
                        ),
                        context=f"ytdlp_comments({video_id})",
                    )
                except Exception:
                    extracted = []
                    comment_status = "ok"
                    collection_engine = None

            if source_engine == "playwright" and not extraction_failed and not extracted:
                try:
                    collection_engine = "playwright"
                    extracted, comment_status = _retry_playwright_call(
                        lambda: pw.get_top_level_comments(
                            video_url=video_url, limit=COMMENT_SCAN_LIMIT
                        ),
                        context=f"playwright_comments({video_id})",
                    )
                except (PlaywrightExtractorError, Exception):
                    extraction_failed = True
                    comment_status = "extraction_failed"
                    failure_reason = "playwright_comment_extraction_failed"

            selected_clean: list[tuple[CommentLike, ProcessedComment]] = []
            if not extraction_failed and comment_status != "comments_disabled":
                selected_clean = _select_clean_top_comments(
                    ranked_comments=_sort_top_comments(extracted),
                    config=config,
                    template_threshold=template_threshold,
                    spam_blacklist=spam_blacklist,
                    global_normalized_counts=global_normalized_counts,
                    global_normalized_samples=global_normalized_samples,
                )

            if extraction_failed:
                comment_status = "extraction_failed"
                if not failure_reason:
                    failure_reason = "comment_extraction_failed"
            elif comment_status == "comments_disabled":
                selected_clean = []
                failure_reason = "comments_disabled"
            elif len(selected_clean) < COMMENTS_PER_VIDEO:
                comment_status = "not_enough_comments"
                failure_reason = "not_enough_clean_comments"
            else:
                comment_status = "ok"
                failure_reason = None

            comments_scanned = len(extracted)
            comments_saved = len(selected_clean)
            comments_filtered = max(0, comments_scanned - comments_saved)

            video_db_id = insert_video(
                conn,
                run_id=run_id,
                channel_db_id=channel_db_id,
                video_id=video_id,
                video_url=video_url,
                title=meta.get("title", ""),
                description=meta.get("description", ""),
                published_at=meta.get("published_at", ""),
                upload_index=upload_index,
                comment_status=comment_status,
                view_count=meta.get("view_count"),
                disclosure_quality=None,
                collection_engine=collection_engine,
                comments_scanned=comments_scanned,
                comments_saved=comments_saved,
                comments_filtered=comments_filtered,
                failure_reason=failure_reason,
                extraction_failed=extraction_failed,
            )
            video_counter += 1

            for rank, (comment, processed) in enumerate(selected_clean, start=1):
                if comment_counter >= MAX_COMMENTS:
                    run_truncated = True
                    break

                insert_comment(
                    conn,
                    run_id=run_id,
                    channel_db_id=channel_db_id,
                    video_db_id=video_db_id,
                    comment_id=comment.comment_id,
                    commenter_hash_id=processed.commenter_hash_id,
                    raw_text=processed.raw_text,
                    cleaned_text=processed.cleaned_text,
                    like_count=int(comment.like_count or 0),
                    reply_count=int(comment.reply_count or 0),
                    published_at=comment.published_at,
                    language=comment.language,
                    comment_rank=rank,
                    is_spam=processed.is_spam,
                    is_template=processed.is_template,
                    is_duplicate=processed.is_duplicate,
                    spam_rule_hits=processed.spam_rule_hits,
                    source_engine=collection_engine or source_engine,
                )
                comment_counter += 1

            if source_engine == "api":
                api_comment_count += len(selected_clean)
            else:
                playwright_comment_count += len(selected_clean)

            if run_truncated:
                break

        if run_truncated:
            break

    return (
        run_truncated,
        api_pool.total_units_used,
        api_comment_count,
        playwright_comment_count,
        {
            "channels_requested": len(targets),
            "coverage_shortfall_channels": coverage_shortfall_channels,
            "no_shorts_available_channels": no_shorts_available_channels,
            "extraction_failed_channels": extraction_failed_channels,
            "niche_attrition": runtime_niche,
        },
    )


def run_batch(
    conn: sqlite3.Connection,
    config: AppConfig,
    targets: list[TargetChannel],
    *,
    template_threshold: float,
    simulate: bool,
    videos_per_channel: int = DEFAULT_MAX_RECENT_VIDEOS_PER_CHANNEL,
    min_expected_videos_per_channel: int = DEFAULT_MIN_EXPECTED_VIDEOS_PER_CHANNEL,
    content_type: str = DEFAULT_CONTENT_TYPE,
    target_file: str | None = None,
    study_profile_name: str | None = None,
    run_payload: dict[str, object] | None = None,
) -> int:
    if not targets:
        raise ValueError("No target channels loaded.")
    if content_type not in {"videos", "shorts"}:
        raise ValueError(f"Unsupported content_type={content_type}. Expected 'videos' or 'shorts'.")

    run_mode = "simulate" if simulate else "live"
    run_id = create_run(
        conn,
        config,
        notes=f"{run_mode};content_type={content_type}",
        content_type=content_type,
        target_file=target_file,
        target_count_requested=len(targets),
        study_profile_name=study_profile_name,
        run_payload=dict(run_payload) if isinstance(run_payload, dict) else None,
    )

    try:
        if simulate:
            run_truncated, api_units_used, api_comment_count, playwright_comment_count, runtime_summary = _run_simulated(
                conn,
                config,
                targets,
                template_threshold=template_threshold,
                run_id=run_id,
            )
        else:
            run_truncated, api_units_used, api_comment_count, playwright_comment_count, runtime_summary = _run_live(
                conn,
                config,
                targets,
                template_threshold=template_threshold,
                run_id=run_id,
                videos_per_channel=videos_per_channel,
                min_expected_videos_per_channel=min_expected_videos_per_channel,
                content_type=content_type,
            )

        qa_report = build_run_qa_report(conn, run_id, runtime_summary=runtime_summary)
        insert_qa_report(conn, run_id, qa_report)

        finalize_run(
            conn,
            run_id,
            status="completed",
            run_truncated=run_truncated,
            api_units_used=api_units_used,
            api_comment_count=api_comment_count,
            playwright_comment_count=playwright_comment_count,
        )
    except Exception:
        finalize_run(conn, run_id, status="failed")
        raise

    return run_id
