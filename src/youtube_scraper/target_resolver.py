from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .pipeline import APIClientPool
from .youtube_api import YouTubeQuotaExceededError


@dataclass
class ResolveStats:
    total: int = 0
    resolved_uc: int = 0
    kept_uc: int = 0
    fallback_handle: int = 0
    fallback_original: int = 0
    failed: int = 0


def _norm(value: str | None) -> str:
    return (value or "").strip()


def _handle_from_url(url: str) -> str:
    u = _norm(url).rstrip("/")
    if "/@" not in u:
        return ""
    return "@" + u.split("/@", 1)[1].split("/", 1)[0].strip()


def _pick_seed_fields(row: dict[str, str]) -> tuple[str, str, str]:
    # Supports both "seed" and internal normalized schemas.
    channel_name = _norm(row.get("channel_name") or row.get("Channel Name"))
    channel_url = _norm(row.get("channel_url") or row.get("Channel URL"))
    niche = _norm(row.get("niche") or row.get("Niche") or row.get("channel_niche"))
    return channel_name, channel_url, niche


def _pick_identifier(row: dict[str, str], channel_name: str, channel_url: str) -> str:
    ident = _norm(row.get("channel_identifier") or row.get("channel_id"))
    if ident:
        return ident
    handle = _handle_from_url(channel_url)
    if handle:
        return handle
    return channel_name


def resolve_targets_to_ids(
    *,
    input_csv: Path,
    output_csv: Path,
    api_keys: list[str],
    quota_per_key: int,
) -> ResolveStats:
    if not api_keys:
        raise ValueError("No API keys configured. Set YOUTUBE_API_KEYS/YOUTUBE_API_KEY in .env.")

    with input_csv.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    pool = APIClientPool(api_keys=api_keys, quota_limit=quota_per_key)
    stats = ResolveStats(total=len(rows))
    out_rows: list[dict[str, str]] = []

    for row in rows:
        channel_name, channel_url, niche = _pick_seed_fields(row)
        if not any([channel_name, channel_url, niche]):
            continue

        source_identifier = _pick_identifier(row, channel_name, channel_url)
        resolution_status = "resolved"
        resolution_note = ""
        final_identifier = source_identifier

        if final_identifier.startswith("UC"):
            stats.kept_uc += 1
        else:
            try:
                resolved = pool.call(
                    lambda c: c.resolve_channel_id(source_identifier or channel_url, channel_name)
                )
                final_identifier = resolved
                stats.resolved_uc += 1
            except YouTubeQuotaExceededError:
                # Keep best effort fallback identifier so pipeline can still try.
                handle = _handle_from_url(channel_url)
                if handle:
                    final_identifier = handle
                    resolution_status = "fallback_handle"
                    resolution_note = "quota_exceeded"
                    stats.fallback_handle += 1
                else:
                    final_identifier = source_identifier
                    resolution_status = "fallback_original"
                    resolution_note = "quota_exceeded"
                    stats.fallback_original += 1
            except Exception as exc:
                handle = _handle_from_url(channel_url)
                if handle:
                    final_identifier = handle
                    resolution_status = "fallback_handle"
                    resolution_note = str(exc)[:160]
                    stats.fallback_handle += 1
                else:
                    final_identifier = source_identifier
                    resolution_status = "failed"
                    resolution_note = str(exc)[:160]
                    stats.failed += 1

        out_rows.append(
            {
                "channel_identifier": final_identifier,
                "channel_name": channel_name,
                "niche": niche,
                "channel_url": channel_url,
                "source_identifier": source_identifier,
                "resolution_status": resolution_status,
                "resolution_note": resolution_note,
            }
        )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "channel_identifier",
                "channel_name",
                "niche",
                "channel_url",
                "source_identifier",
                "resolution_status",
                "resolution_note",
            ],
        )
        writer.writeheader()
        writer.writerows(out_rows)

    return stats
