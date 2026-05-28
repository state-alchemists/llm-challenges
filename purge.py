#!/usr/bin/env python3
"""Purge cells from experiment/results.json and their trial directories.

By default this is a DRY RUN — it lists what would be removed without touching
anything. Pass --yes to actually delete.

Examples:
    # Preview every ERROR cell that would be purged
    python3 purge.py --status ERROR

    # Actually remove every ERROR cell
    python3 purge.py --status ERROR --yes

    # Remove every cell for a specific model
    python3 purge.py --model bsim:bedrock.amazon.nova-lite-v1:0 --yes

    # Remove every ERROR cell for a specific model on a specific test case
    python3 purge.py --status ERROR --model bsim:bedrock.deepseek.v3.2 \
                     --test-case refactor --yes

    # Multiple filters: pass each flag multiple times to OR within a category
    python3 purge.py --status ERROR --status TIMEOUT --yes

After deletion, the next `zrb-llm-evaluator run --output-dir ./experiment`
will re-attempt the purged cells (resume support only skips cells with
terminal status still in results.json).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


DEFAULT_RESULTS = Path(__file__).parent / "experiment" / "results.json"


def matches(d: dict, statuses: set[str], models: set[str], test_cases: set[str]) -> bool:
    if statuses and d.get("status") not in statuses:
        return False
    if models and d.get("model") not in models:
        return False
    if test_cases and d.get("test_case") not in test_cases:
        return False
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=DEFAULT_RESULTS,
        help="Path to results.json (default: experiment/results.json beside this script)",
    )
    parser.add_argument("--status", action="append", default=[],
                        help="Status to purge (repeatable). E.g. ERROR, FAIL, TIMEOUT")
    parser.add_argument("--model", action="append", default=[],
                        help="Model to purge (repeatable). Full ID, e.g. bsim:bedrock.deepseek.v3.2")
    parser.add_argument("--test-case", action="append", default=[],
                        help="Test case name to purge (repeatable). E.g. bug-fix")
    parser.add_argument("--yes", action="store_true",
                        help="Actually delete. Without this flag, run is a dry-run preview.")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip writing a results.json.bak.<timestamp> backup.")
    args = parser.parse_args(argv)

    if not args.status and not args.model and not args.test_case:
        parser.error("Provide at least one of --status, --model, --test-case.")

    results_path: Path = args.results
    if not results_path.is_file():
        print(f"results.json not found at {results_path}", file=sys.stderr)
        return 1

    data = json.loads(results_path.read_text(encoding="utf-8"))
    statuses = set(args.status)
    models = set(args.model)
    test_cases = set(args.test_case)

    drop = [d for d in data if matches(d, statuses, models, test_cases)]
    keep = [d for d in data if not matches(d, statuses, models, test_cases)]

    if not drop:
        print("No cells matched the filter — nothing to purge.")
        return 0

    print(f"Filter:    status={sorted(statuses) or '*'}  "
          f"model={sorted(models) or '*'}  test_case={sorted(test_cases) or '*'}")
    print(f"Would remove {len(drop)} of {len(data)} cells "
          f"(would keep {len(keep)}).")

    by_model = Counter(d["model"] for d in drop)
    print("\nBy model:")
    for m, n in by_model.most_common():
        statuses_for_m = Counter(d["status"] for d in drop if d["model"] == m)
        print(f"  {m}: {n}  ({dict(statuses_for_m)})")

    # Trial directories implied by stdout_log_path's parent
    trial_dirs: set[Path] = set()
    missing_logs = 0
    for d in drop:
        log = d.get("stdout_log_path")
        if log:
            trial_dirs.add(Path(log).parent)
        else:
            missing_logs += 1
    existing_dirs = [td for td in trial_dirs if td.exists()]
    print(f"\nTrial directories to remove: {len(existing_dirs)} "
          f"(of {len(trial_dirs)} referenced; {missing_logs} cells had no stdout_log_path)")

    if not args.yes:
        print("\nDRY RUN — pass --yes to actually delete.")
        return 0

    # Backup
    if not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = results_path.with_suffix(f".json.bak.{ts}")
        shutil.copy2(results_path, backup)
        print(f"\nBackup: {backup}")

    # Atomic write
    tmp = results_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(keep, indent=2), encoding="utf-8")
    tmp.replace(results_path)
    print(f"results.json: {len(data)} -> {len(keep)} (removed {len(drop)})")

    # Remove trial directories
    removed = 0
    for td in existing_dirs:
        shutil.rmtree(td)
        removed += 1
    print(f"Removed {removed} trial directories")

    # Clean up empty parent directories
    exp_root = results_path.parent
    pruned = 0
    for model_dir in exp_root.iterdir():
        if not model_dir.is_dir():
            continue
        for tc_dir in list(model_dir.iterdir()):
            if tc_dir.is_dir() and not any(tc_dir.iterdir()):
                tc_dir.rmdir()
                pruned += 1
        if model_dir.is_dir() and not any(model_dir.iterdir()):
            model_dir.rmdir()
            pruned += 1
    if pruned:
        print(f"Removed {pruned} empty parent directories")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
