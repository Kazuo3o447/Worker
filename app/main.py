"""GEMA Azure Blob Storage Classification Worker – entry point.

Usage:
    python -m app.main --mode scan     [--max-files 50] [--prefix folder/]
    python -m app.main --mode classify [--max-files 50] [--dry-run] [--force]
                                       [--enable-ai] [--ai-provider foundry]
                                       [--ai-max-calls 20]

Exit codes:
    0  – run completed (even with per-blob errors)
    1  – unrecoverable logic error
    2  – cannot connect to Azure Storage
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from app import logging_utils
from app.azure_blob_repository import AzureBlobRepository
from app.config import load_config
from app.logging_utils import log_error
from app.worker import run_classify, run_scan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.main",
        description="GEMA Azure Blob Storage Classification Worker",
    )
    parser.add_argument(
        "--mode",
        choices=["scan", "classify"],
        required=True,
        help="scan = read-only detection; classify = write tags + upload reports",
    )
    parser.add_argument("--max-files", type=int, default=None, metavar="N",
                        help="Max blobs per run (default from DEFAULT_MAX_FILES env)")
    parser.add_argument("--prefix", type=str, default=None, metavar="PATH",
                        help="Only process blobs starting with this prefix")
    parser.add_argument("--force", action="store_true", default=False,
                        help="Re-classify already-tagged blobs")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Run without writing tags/metadata to Azure")
    # AI overrides
    parser.add_argument("--enable-ai", action="store_true", default=False,
                        help="Enable AI classification (overrides ENABLE_AI env)")
    parser.add_argument("--ai-provider", type=str, default=None,
                        metavar="foundry|none",
                        help="AI provider (overrides AI_PROVIDER env)")
    parser.add_argument("--ai-max-calls", type=int, default=None, metavar="N",
                        help="Max AI calls per run (overrides AI_MAX_CALLS_PER_RUN env)")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = load_config()

    # Apply CLI overrides
    if args.enable_ai:
        config.enable_ai = True
    if args.ai_provider is not None:
        config.ai_provider = args.ai_provider
    if args.ai_max_calls is not None:
        config.ai_max_calls_per_run = args.ai_max_calls

    run_id = _generate_run_id()

    # Enable in-memory event buffering (events written to Azure at run end)
    logging_utils.enable_event_buffering()

    # Connectivity check
    try:
        repo = AzureBlobRepository(config)
        if not repo.ping():
            log_error(
                run_id,
                "Cannot reach Azure Storage – check credentials and container names.",
                storage_account=config.storage_account,
                source_container=config.source_container,
                auth_mode=config.auth_mode,
            )
            return 2
    except Exception as exc:  # noqa: BLE001
        log_error(run_id, "Failed to initialise Azure Blob Repository", error=str(exc))
        return 2

    # Optional AI client
    ai_client = None
    if config.enable_ai and config.ai_provider == "foundry":
        from app.ai_foundry_client import AIFoundryClient  # noqa: PLC0415
        ai_client = AIFoundryClient(config)
        if not ai_client.available:
            log_error(run_id, f"AI client unavailable: {ai_client.init_error}")
            # Non-fatal: continue without AI

    max_files = args.max_files if args.max_files is not None else config.default_max_files
    prefix = args.prefix

    if args.mode == "scan":
        return run_scan(
            run_id=run_id, config=config, repo=repo,
            prefix=prefix, max_files=max_files, dry_run=args.dry_run,
        )
    if args.mode == "classify":
        return run_classify(
            run_id=run_id, config=config, repo=repo,
            prefix=prefix, max_files=max_files,
            dry_run=args.dry_run, force=args.force,
            ai_client=ai_client,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
