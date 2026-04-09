from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from .auto_analysis import export_auto_analysis
from .conformity_cascade import run_from_csv
from .conformity_robustness import export_robustness_suite
from .config import load_config
from .db import get_connection, init_database
from .exploratory_report import export_exploratory_report
from .exporter import export_run_datasets
from .paper_figures import export_paper_figure_pack
from .pipeline import load_targets_csv, run_batch
from .target_resolver import resolve_targets_to_ids


def _latest_run_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def cmd_init_db(_: argparse.Namespace) -> None:
    config = load_config()
    init_database(config)
    print(f"Initialized SQLite DB at: {config.database_path}")


def cmd_run_batch(args: argparse.Namespace) -> None:
    config = load_config()
    init_database(config)

    targets = load_targets_csv(Path(args.targets))
    if args.channel_limit is not None:
        targets = targets[: args.channel_limit]

    with get_connection(config.database_path) as conn:
        run_payload = {
            "scrape": {
                "targets_csv": str(args.targets),
                "execution_mode": config.execution_mode,
                "content_type": args.content_type,
                "channel_limit": args.channel_limit,
                "videos_per_channel": args.videos_per_channel,
                "min_expected_videos_per_channel": args.min_expected_videos_per_channel,
                "template_threshold": args.template_threshold,
                "simulate": args.simulate,
                "study_profile_name": "",
            },
            "dataset_filters": {},
            "run_meta": {
                "target_file": str(args.targets),
                "study_profile_name": "",
            },
        }
        run_id = run_batch(
            conn,
            config,
            targets,
            template_threshold=args.template_threshold,
            simulate=args.simulate,
            videos_per_channel=args.videos_per_channel,
            min_expected_videos_per_channel=args.min_expected_videos_per_channel,
            content_type=args.content_type,
            target_file=str(args.targets),
            study_profile_name=None,
            run_payload=run_payload,
        )
    print(f"Batch complete. run_id={run_id}")


def cmd_export_csv(args: argparse.Namespace) -> None:
    config = load_config()
    init_database(config)

    out_dir = Path(args.out_dir)
    with get_connection(config.database_path) as conn:
        run_id = args.run_id or _latest_run_id(conn)
        if run_id is None:
            raise RuntimeError("No runs found. Execute run-batch first.")
        files = export_run_datasets(conn, run_id, out_dir)

    print("Exported CSV files:")
    for name, path in files.items():
        print(f"- {name}: {path}")


def cmd_auto_analyze(args: argparse.Namespace) -> None:
    config = load_config()
    init_database(config)

    out_dir = Path(args.out_dir)
    with get_connection(config.database_path) as conn:
        run_id = args.run_id or _latest_run_id(conn)
        if run_id is None:
            raise RuntimeError("No runs found. Execute run-batch first.")
        files = export_auto_analysis(
            conn,
            run_id,
            out_dir,
            include_flagged=args.include_flagged,
        )

    print("Exported auto-analysis CSV files:")
    for name, path in files.items():
        print(f"- {name}: {path}")


def cmd_exploratory_report(args: argparse.Namespace) -> None:
    config = load_config()
    init_database(config)

    out_dir = Path(args.out_dir)
    with get_connection(config.database_path) as conn:
        run_id = args.run_id or _latest_run_id(conn)
        if run_id is None:
            raise RuntimeError("No runs found. Execute run-batch first.")
        files = export_exploratory_report(
            conn,
            run_id,
            out_dir,
            include_flagged=args.include_flagged,
            min_ai_signal_comments=args.min_ai_signal_comments,
        )

    print("Exported exploratory report files:")
    for name, path in files.items():
        print(f"- {name}: {path}")


def cmd_resolve_targets(args: argparse.Namespace) -> None:
    config = load_config()
    stats = resolve_targets_to_ids(
        input_csv=Path(args.input),
        output_csv=Path(args.output),
        api_keys=config.youtube_api_keys,
        quota_per_key=config.api_daily_quota,
    )
    print(f"Resolved targets written to: {args.output}")
    print(
        "Stats:"
        f" total={stats.total}"
        f" kept_uc={stats.kept_uc}"
        f" resolved_uc={stats.resolved_uc}"
        f" fallback_handle={stats.fallback_handle}"
        f" fallback_original={stats.fallback_original}"
        f" failed={stats.failed}"
    )


def cmd_conformity_cascade(args: argparse.Namespace) -> None:
    result = run_from_csv(
        input_csv=Path(args.input_csv),
        output_ranked_csv=Path(args.out_ranked_csv) if args.out_ranked_csv else None,
        output_response_csv=Path(args.out_response_csv) if args.out_response_csv else None,
        output_effects_csv=Path(args.out_effects_csv) if args.out_effects_csv else None,
        output_icc_csv=Path(args.out_icc_csv) if args.out_icc_csv else None,
    )
    print("Conformity cascade model summary:")
    print(result.model_summary)
    print("\nFixed effects (log-odds, OR, 95% CI, p-value):")
    print(result.effects_df.to_string(index=False))
    print("\nICC table:")
    print(result.icc_df.to_string(index=False))
    print(
        "Rows:"
        f" ranked={len(result.ranked_df)}"
        f" response_ranks_2_20={len(result.response_df)}"
        f" videos={len(result.top_comment_skeptical)}"
    )


def cmd_conformity_robustness(args: argparse.Namespace) -> None:
    config = load_config()
    init_database(config)

    with get_connection(config.database_path) as conn:
        files = export_robustness_suite(
            conn,
            run_ids=args.run_ids,
            out_dir=Path(args.out_dir),
            include_flagged=args.include_flagged,
            non_shorts_only=not args.include_shorts,
            min_response_comments=args.min_response_comments,
        )

    print("Exported conformity robustness files:")
    for name, path in files.items():
        print(f"- {name}: {path}")


def cmd_paper_figure_pack(args: argparse.Namespace) -> None:
    config = load_config()
    init_database(config)

    with get_connection(config.database_path) as conn:
        payload = export_paper_figure_pack(
            conn,
            out_dir=Path(args.out_dir),
            freeze_id=args.freeze_id,
            freeze_name=args.freeze_name,
            include_flagged=args.include_flagged,
        )

    manifest = payload.get("manifest", {})
    print("Paper figure pack generated:")
    print(
        f"- freeze: {manifest.get('freeze_name')} "
        f"(id={manifest.get('freeze_id')}, uuid={manifest.get('freeze_uuid')})"
    )
    print(f"- run_ids: {manifest.get('run_ids_included')}")
    print(f"- resolved_comment_count: {manifest.get('resolved_comment_count')}")
    print(
        "- H1 headline: "
        f"OR={manifest.get('headline_h1_odds_ratio')} "
        f"p={manifest.get('headline_h1_p_value_approx')}"
    )
    print(
        "- reproducibility pass: "
        f"{manifest.get('reproducibility_summary', {}).get('pass_within_tolerance')}"
    )
    print("Files:")
    for name, path in payload.get("files", {}).items():
        print(f"- {name}: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YouTube scraper research CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="Initialize SQLite schema")
    p_init.set_defaults(func=cmd_init_db)

    p_run = sub.add_parser("run-batch", help="Run extraction batch")
    p_run.add_argument(
        "--targets",
        required=True,
        help=(
            "CSV with either "
            "[channel_id,channel_url,channel_niche] "
            "or [channel_identifier,channel_name,niche]"
        ),
    )
    p_run.add_argument("--channel-limit", type=int, default=None, help="Optional channel limit")
    p_run.add_argument(
        "--videos-per-channel",
        type=int,
        default=80,
        help="Max recent videos per channel to scan (pilot recommended: 20)",
    )
    p_run.add_argument(
        "--min-expected-videos-per-channel",
        type=int,
        default=30,
        help="Threshold for coverage_shortfall flag (pilot recommended: 20)",
    )
    p_run.add_argument(
        "--content-type",
        choices=["videos", "shorts"],
        default="videos",
        help="Collect regular long-form videos or Shorts (separate runs).",
    )
    p_run.add_argument("--template-threshold", type=float, default=0.90, help="Template similarity threshold")
    p_run.add_argument(
        "--simulate",
        action="store_true",
        help="Run deterministic simulated extraction (safe for scaffold testing)",
    )
    p_run.set_defaults(func=cmd_run_batch)

    p_export = sub.add_parser("export-csv", help="Export run datasets for R")
    p_export.add_argument("--run-id", type=int, default=None, help="Run ID to export; default latest")
    p_export.add_argument("--out-dir", default="exports", help="Output directory")
    p_export.set_defaults(func=cmd_export_csv)

    p_auto = sub.add_parser("auto-analyze", help="Run automatic rules-based comment analysis")
    p_auto.add_argument("--run-id", type=int, default=None, help="Run ID to analyze; default latest")
    p_auto.add_argument("--out-dir", default="exports", help="Output directory")
    p_auto.add_argument(
        "--include-flagged",
        action="store_true",
        help="Include spam/template/duplicate rows in auto-analysis (default: excluded).",
    )
    p_auto.set_defaults(func=cmd_auto_analyze)

    p_explore = sub.add_parser(
        "exploratory-report",
        help="Export no-disclosure + AI-signal exploratory report tables",
    )
    p_explore.add_argument("--run-id", type=int, default=None, help="Run ID to analyze; default latest")
    p_explore.add_argument("--out-dir", default="exports", help="Output directory")
    p_explore.add_argument(
        "--include-flagged",
        action="store_true",
        help="Include spam/template/duplicate rows in exploratory report (default: excluded).",
    )
    p_explore.add_argument(
        "--min-ai-signal-comments",
        type=int,
        default=1,
        help="Minimum AI-signal comments per no-disclosure video to keep in candidate list.",
    )
    p_explore.set_defaults(func=cmd_exploratory_report)

    p_resolve = sub.add_parser(
        "resolve-targets",
        help="Resolve channel names/handles to stable UC channel IDs using YouTube API",
    )
    p_resolve.add_argument(
        "--input",
        required=True,
        help="Input CSV (seed list or existing targets).",
    )
    p_resolve.add_argument(
        "--output",
        default="data/targets_resolved.csv",
        help="Output CSV with channel_identifier/channel_name/niche.",
    )
    p_resolve.set_defaults(func=cmd_resolve_targets)

    p_conform = sub.add_parser(
        "conformity-cascade",
        help="Run conformity cascade model from a CSV with is_skeptical labels.",
    )
    p_conform.add_argument(
        "--input-csv",
        required=True,
        help=(
            "CSV with columns: video_id, channel_id, channel_niche, comment_text, like_count, "
            "comment_timestamp, is_skeptical"
        ),
    )
    p_conform.add_argument(
        "--out-ranked-csv",
        default=None,
        help="Optional output path for ranked comments dataframe.",
    )
    p_conform.add_argument(
        "--out-response-csv",
        default=None,
        help="Optional output path for response dataframe (ranks 2..20).",
    )
    p_conform.add_argument(
        "--out-effects-csv",
        default=None,
        help="Optional output path for fixed-effects table.",
    )
    p_conform.add_argument(
        "--out-icc-csv",
        default=None,
        help="Optional output path for ICC table.",
    )
    p_conform.set_defaults(func=cmd_conformity_cascade)

    p_conform_robust = sub.add_parser(
        "conformity-robustness",
        help="Run conformity robustness suite from DB runs (non-Shorts by default).",
    )
    p_conform_robust.add_argument(
        "--run-ids",
        nargs="+",
        required=True,
        type=int,
        help="Run IDs to combine (example: --run-ids 11 17 18).",
    )
    p_conform_robust.add_argument(
        "--out-dir",
        default="exports",
        help="Output directory for input/ranked/response/effects CSV files.",
    )
    p_conform_robust.add_argument(
        "--include-flagged",
        action="store_true",
        help="Include spam/template/duplicate comments (default: excluded).",
    )
    p_conform_robust.add_argument(
        "--include-shorts",
        action="store_true",
        help="Include Shorts URLs in analysis (default: non-Shorts only).",
    )
    p_conform_robust.add_argument(
        "--min-response-comments",
        type=int,
        default=10,
        help="Minimum response comments for the min-comments robustness model (default: 10).",
    )
    p_conform_robust.set_defaults(func=cmd_conformity_robustness)

    p_paper_fig = sub.add_parser(
        "paper-figure-pack",
        help="Generate paper-ready figure tables/charts from a named evidence freeze.",
    )
    p_paper_fig.add_argument(
        "--out-dir",
        default="exports/paper_figures",
        help="Output directory for figure tables/charts.",
    )
    p_paper_fig.add_argument(
        "--freeze-id",
        type=int,
        default=None,
        help="Use a specific freeze ID (default: latest freeze).",
    )
    p_paper_fig.add_argument(
        "--freeze-name",
        default=None,
        help="Use a specific freeze name (default: latest freeze).",
    )
    p_paper_fig.add_argument(
        "--include-flagged",
        action="store_true",
        help="Include spam/template/duplicate rows in model input (default: excluded).",
    )
    p_paper_fig.set_defaults(func=cmd_paper_figure_pack)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
