"""Validator for the debug-loop challenge.

Two-stage check:
1. Executable: ``./run.sh`` exits 0 and prints ``OK``.
2. Trajectory: the agent actually iterated — the recorded TrialTrace
   must show the script was run at least twice with file edits between
   runs, demonstrating self-correction rather than a lucky one-shot fix.

Trajectory check is BONUS — score 1.0 / EXCELLENT requires it, score 0.7 /
PASS for "fixed but no observable iteration". This rewards models that
genuinely use a debug loop without punishing a model that happens to
prepare both fixes mentally before any tool call.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from zrb_llm_evaluator.models import TrialTrace, ValidationCheck, ValidationResult
from zrb_llm_evaluator.protocols import ValidatorProtocol

# Tool names (substring match) that indicate executing the script.
EXEC_TOOL_HINTS = ("bash", "run_command", "shell", "execute", "cmd")
# Tool names that indicate editing a file.
EDIT_TOOL_HINTS = ("write", "edit", "patch", "replace", "str_replace")

# Suspicious bypasses we explicitly reject — instruction forbids them.
# Both are line-anchored, so every match here needs re.MULTILINE: without it
# `$` means end-of-string and `TRY_BYPASS` only fires on a file that *ends*
# in `try:`, i.e. never on the bypass it exists to catch.
EXIT_ZERO_BYPASS = r"^\s*exit\s+0\s*$"  # bash 'exit 0' as a line
TRY_BYPASS = r"^\s*try\s*:\s*$"  # try/except wrapping the offending code


def _has_bypass(workdir: Path) -> str | None:
    pipeline = workdir / "pipeline.py"
    if not pipeline.is_file():
        return "pipeline.py missing"
    # Any module the fix could touch, not just pipeline.py — a try/except in
    # config.py swallows the error just as well.
    for src in sorted(workdir.glob("*.py")):
        if re.search(TRY_BYPASS, src.read_text(encoding="utf-8"), re.MULTILINE):
            return f"{src.name} wraps the failure in try/except"
    run_sh = workdir / "run.sh"
    if not run_sh.is_file():
        return "run.sh missing"
    sh_text = run_sh.read_text(encoding="utf-8")
    if re.search(EXIT_ZERO_BYPASS, sh_text, re.MULTILINE):
        return "run.sh contains an unconditional 'exit 0'"
    return None


def _count_iterations(trace: TrialTrace | None) -> tuple[int, int]:
    """Return (exec_runs, edits) from the trace tool calls."""
    if trace is None:
        return 0, 0
    exec_runs = 0
    edits = 0
    for tc in trace.tool_calls:
        lname = tc.name.lower()
        if any(h in lname for h in EXEC_TOOL_HINTS):
            # Only calls that actually invoked the script count as iterations;
            # an `ls` is not a debug loop. (The previous branch here counted
            # every shell call, then claimed in a comment to weight them less.)
            blob = " ".join(str(v) for v in tc.args.values())
            if "run.sh" in blob or "pipeline.py" in blob:
                exec_runs += 1
        elif any(h in lname for h in EDIT_TOOL_HINTS):
            edits += 1
    return exec_runs, edits


class DebugLoopValidator:
    def validate(
        self,
        output_dir: Path,
        log_content: str,
        trace: TrialTrace | None = None,
    ) -> ValidationResult:
        details: list[ValidationCheck] = []

        run_sh = output_dir / "run.sh"
        if not run_sh.is_file():
            details.append(
                ValidationCheck(
                    name="run_sh_present",
                    passed=False,
                    message="run.sh missing — agent deleted the entry script",
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)

        bypass = _has_bypass(output_dir)
        if bypass:
            details.append(
                ValidationCheck(
                    name="no_bypass",
                    passed=False,
                    message=f"Bypass detected — {bypass}. Instruction forbids exit 0 / try-except.",
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)
        details.append(
            ValidationCheck(
                name="no_bypass",
                passed=True,
                message="No exit 0 / try-except bypass detected",
            )
        )

        try:
            proc = subprocess.run(
                ["bash", "run.sh"],
                cwd=str(output_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            details.append(
                ValidationCheck(
                    name="run_sh_exits_clean",
                    passed=False,
                    message="run.sh exceeded 30s — likely a hang in the fix",
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)

        ok_exit = proc.returncode == 0
        # run.sh ends in `echo OK` and must not be modified, so the last line
        # is exactly "OK" — a substring test would also accept "NOT OK".
        ok_marker = proc.stdout.strip().splitlines()[-1].strip() == "OK" if proc.stdout.strip() else False
        details.append(
            ValidationCheck(
                name="run_sh_exits_clean",
                passed=ok_exit and ok_marker,
                message=(
                    f"exit={proc.returncode}, last_line={proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else '<empty>'!r}"
                ),
            )
        )

        if not (ok_exit and ok_marker):
            return ValidationResult(status="FAIL", score=0.0, details=details)

        exec_runs, edits = _count_iterations(trace)
        iterated = exec_runs >= 2 and edits >= 2
        details.append(
            ValidationCheck(
                name="observed_iteration",
                passed=iterated,
                message=f"trace: {exec_runs} script execution(s), {edits} file edit(s) "
                "(EXCELLENT needs ≥2 of each)",
            )
        )

        if iterated:
            return ValidationResult(status="EXCELLENT", score=1.0, details=details)
        return ValidationResult(status="PASS", score=0.7, details=details)


validator = DebugLoopValidator()
