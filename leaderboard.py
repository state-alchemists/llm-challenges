#!/usr/bin/env python3
"""Print a leaderboard and failure analysis of experiment/results.json."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


ERROR_PATTERNS: dict[str, str] = {
    "429_throttle (Bedrock)": r"ThrottlingException",
    "400_validation (Bedrock)": r"ValidationException",
    "404_notfound (Bedrock)": r"ResourceNotFoundException",
    "access_denied (Bedrock)": r"AccessDeniedException",
    "empty_stream (proxy/tool-call)": r"Streamed response ended without content",
    "middleware_429 (per-user limit)": r"LLM Middleware's per-user rate limit",
    "google_404 (model not found)": r"status_code: 404, model_name: gemini",
    "google_429 (Google rate limit)": r"status_code: 429, model_name: gemini",
    "timeout": r"asyncio\.TimeoutError|TimeoutException",
    "tool_retry_exceeded": r"ToolRetryError|exceeded the retry limit",
}


def classify_error(content: str) -> str:
    hits = [name for name, pat in ERROR_PATTERNS.items() if re.search(pat, content)]
    return ",".join(hits) if hits else "OTHER"


def extract_upstream_model(content: str) -> str | None:
    m = re.search(r"model_name: ([^,\s]+)", content)
    return m.group(1).strip() if m else None


def fmt_cells(c: Counter) -> str:
    return (
        f"EXC={c.get('EXCELLENT', 0):3d}  "
        f"PASS={c.get('PASS', 0):2d}  "
        f"FAIL={c.get('FAIL', 0):2d}  "
        f"ERR={c.get('ERROR', 0):2d}  "
        f"TIMEOUT={c.get('TIMEOUT', 0):2d}"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default=str(Path(__file__).parent / "experiment" / "results.json"),
        help="Path to results.json (default: experiment/results.json beside this script)",
    )
    args = parser.parse_args(argv)

    path = Path(args.results)
    if not path.is_file():
        print(f"results.json not found at {path}", file=sys.stderr)
        return 1

    data = json.loads(path.read_text(encoding="utf-8"))
    if not data:
        print("results.json is empty.")
        return 0

    total = len(data)
    overall = Counter(d["status"] for d in data)
    print(f"Total cells: {total}")
    print(f"Overall:     {dict(overall)}")

    # ---- Leaderboard ----
    by_model: dict[str, Counter] = defaultdict(Counter)
    scores_by: dict[str, list[float]] = defaultdict(list)
    for d in data:
        by_model[d["model"]][d["status"]] += 1
        vr = d.get("verification_result") or {}
        s = vr.get("score")
        if s is not None:
            scores_by[d["model"]].append(float(s))

    def rank_key(item: tuple[str, Counter]) -> tuple:
        m, c = item
        n = sum(c.values())
        ok = c.get("EXCELLENT", 0) + c.get("PASS", 0)
        pass_rate = ok / n if n else 0.0
        excellent = c.get("EXCELLENT", 0)
        scores = scores_by.get(m, [])
        avg = sum(scores) / len(scores) if scores else -1.0
        # Rank order:
        #   1. pass rate (status-level outcomes — what actually worked)
        #   2. EXCELLENT count (quality among passes)
        #   3. avg validator score (granular tiebreaker)
        # Putting pass rate first avoids letting a validator that scores a
        # FAIL leniently (e.g., 1.0 alongside status=FAIL) buoy a model
        # above one that actually passed every challenge.
        return (-pass_rate, -excellent, -avg)

    print("\nLeaderboard (sorted by pass rate, then EXCELLENT count, then avg score):")
    print(
        f"  {'#':>2}  {'model':50s}  {'avg':>5s}  {'pass':>4s}  {'n':>3s}  cells"
    )
    print(f"  {'-'*2}  {'-'*50}  {'-'*5}  {'-'*4}  {'-'*3}  -----")
    for i, (m, c) in enumerate(sorted(by_model.items(), key=rank_key), start=1):
        n = sum(c.values())
        ok = c.get("EXCELLENT", 0) + c.get("PASS", 0)
        rate = (100 * ok // n) if n else 0
        scores = scores_by.get(m, [])
        avg = sum(scores) / len(scores) if scores else 0.0
        print(
            f"  {i:>2}  {m:50s}  {avg:5.3f}  {rate:3d}%  {len(scores):>3d}  {fmt_cells(c)}"
        )

    # ---- By test case ----
    print("\nBy test case:")
    by_tc: dict[str, Counter] = defaultdict(Counter)
    for d in data:
        by_tc[d["test_case"]][d["status"]] += 1
    print(f"  {'test_case':20s}  {'pass':>4s}  {'n':>3s}  cells")
    print(f"  {'-'*20}  {'-'*4}  {'-'*3}  -----")
    for tc in sorted(by_tc):
        c = by_tc[tc]
        n = sum(c.values())
        ok = c.get("EXCELLENT", 0) + c.get("PASS", 0)
        rate = (100 * ok // n) if n else 0
        print(f"  {tc:20s}  {rate:3d}%  {n:>3d}  {fmt_cells(c)}")

    # ---- Error analysis ----
    err_cells = [d for d in data if d["status"] == "ERROR"]
    if err_cells:
        causes: dict[str, Counter] = defaultdict(Counter)
        upstream: dict[str, Counter] = defaultdict(Counter)
        no_log: dict[str, int] = defaultdict(int)
        for d in err_cells:
            log = d.get("stdout_log_path")
            if not log or not os.path.exists(log):
                no_log[d["model"]] += 1
                causes[d["model"]]["NO_LOG"] += 1
                continue
            try:
                content = Path(log).read_text(errors="ignore")
            except OSError:
                no_log[d["model"]] += 1
                continue
            causes[d["model"]][classify_error(content)] += 1
            um = extract_upstream_model(content)
            if um:
                upstream[d["model"]][um] += 1

        print("\nERROR causes (only ERROR cells):")
        for m in sorted(causes):
            print(f"  {m}: {dict(causes[m])}")
            if m in upstream:
                # only show when upstream differs from requested
                interesting = {k: v for k, v in upstream[m].items() if k not in m}
                if interesting:
                    print(f"    upstream model_name seen in error body: {dict(interesting)}")

    # ---- FAIL analysis ----
    fail_cells = [d for d in data if d["status"] == "FAIL"]
    if fail_cells:
        # Per (model, test_case), aggregate failing validator-check names
        fail_checks: dict[tuple[str, str], Counter] = defaultdict(Counter)
        for d in fail_cells:
            key = (d["model"], d["test_case"])
            for ck in (d.get("verification_result") or {}).get("details", []):
                if not ck.get("passed", True):
                    fail_checks[key][ck.get("name", "?")] += 1
        print("\nFAIL — most common failing validator checks per (model, test_case):")
        for key in sorted(fail_checks):
            top = fail_checks[key].most_common(5)
            print(f"  {key[0]} / {key[1]}: " + ", ".join(f"{n}x {name}" for name, n in top))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
