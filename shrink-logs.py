#!/usr/bin/env python3
"""Compress oversized trial stdout logs so the experiment stays committable.

GitHub rejects any single file over 100 MiB on push and warns above 50 MiB. A
handful of trials produce stdout logs far past that — usually because the agent
ran a bare `git diff`/`git status` inside the enclosing repo, whose tracked
`experiment/` holds prior trials' history JSONs, each embedding a serialized
system prompt. One such log reached 112 MB from ~2700 repetitions of it.

Those logs are worth keeping: for a trial killed at the timeout the history JSON
is empty (2 bytes) or absent, so `stdout.log` is the *only* record of what the
agent was doing. Deleting them destroys the evidence; compressing them does not
(112 MB -> ~21 MB, comfortably under both limits).

This replaces `stdout.log` with `stdout.log.gz` for every log above
``--threshold-mb``. Read one back with `zcat <path>.gz` (or `gzcat` on macOS).

Safe for the tooling: `zrb-llm-evaluator report` only prints
``stdout_log_path``, it never opens the file (see ``reporter.py``), so
regenerating the report still works. A re-run of a purged cell recreates the
log from scratch.

By default this is a DRY RUN — it lists what would be compressed without
touching anything. Pass --yes to actually do it.

Examples:
    # Preview every log that would be compressed (default threshold: 50 MB)
    python3 shrink-logs.py

    # Actually compress them
    python3 shrink-logs.py --yes

    # Only the ones GitHub would hard-block
    python3 shrink-logs.py --threshold-mb 100 --yes

    # Keep the uncompressed copy on disk as well
    python3 shrink-logs.py --yes --keep-original
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sys
from pathlib import Path

MIB = 1024 * 1024
DEFAULT_THRESHOLD_MB = 50
LOG_GLOB = "*/*/trial-*/stdout.log"


def find_oversized(experiment_dir: Path, threshold_bytes: int) -> list[tuple[Path, int]]:
    """Return (path, size) for each stdout log at or above *threshold_bytes*."""
    found: list[tuple[Path, int]] = []
    for path in sorted(experiment_dir.glob(LOG_GLOB)):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size >= threshold_bytes:
            found.append((path, size))
    return sorted(found, key=lambda item: item[1], reverse=True)


def compress(path: Path, keep_original: bool) -> int:
    """Gzip *path* to ``<path>.gz`` and return the compressed size.

    Streams rather than reading the file into memory — these are 100 MB+ files.
    The original is removed unless *keep_original*; the ``.gz`` is written first
    so an interrupted run never loses the log.
    """
    target = path.with_suffix(path.suffix + ".gz")
    with open(path, "rb") as src, gzip.open(target, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst, length=4 * MIB)
    size = target.stat().st_size
    if not keep_original:
        path.unlink()
    return size


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compress oversized trial stdout logs (dry run unless --yes).",
    )
    parser.add_argument(
        "--dir",
        default="./experiment",
        help="Experiment output directory (default: ./experiment)",
    )
    parser.add_argument(
        "--threshold-mb",
        type=float,
        default=DEFAULT_THRESHOLD_MB,
        help=f"Compress logs at or above this size (default: {DEFAULT_THRESHOLD_MB})",
    )
    parser.add_argument(
        "--keep-original",
        action="store_true",
        help="Leave the uncompressed log in place as well",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually compress; without this the script only reports",
    )
    args = parser.parse_args()

    experiment_dir = Path(args.dir)
    if not experiment_dir.is_dir():
        print(f"error: {experiment_dir} is not a directory", file=sys.stderr)
        return 1

    threshold_bytes = int(args.threshold_mb * MIB)
    oversized = find_oversized(experiment_dir, threshold_bytes)
    if not oversized:
        print(f"No stdout log at or above {args.threshold_mb:g} MB under {experiment_dir}.")
        return 0

    verb = "Compressing" if args.yes else "Would compress"
    print(f"{verb} {len(oversized)} log(s) at or above {args.threshold_mb:g} MB:\n")
    total_before = total_after = 0
    for path, size in oversized:
        total_before += size
        if args.yes:
            after = compress(path, args.keep_original)
            total_after += after
            print(f"  {size / MIB:8.1f} MB -> {after / MIB:6.1f} MB  {path}.gz")
        else:
            print(f"  {size / MIB:8.1f} MB  {path}")

    if args.yes:
        saved = total_before - total_after
        print(
            f"\nDone. {total_before / MIB:.1f} MB -> {total_after / MIB:.1f} MB "
            f"({saved / MIB:.1f} MB saved). Read one with: zcat <path>.gz"
        )
    else:
        print(f"\n{total_before / MIB:.1f} MB total. Re-run with --yes to compress.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
