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
BYPASS_PATTERNS = (
    r"^\s*exit\s+0\s*$",  # bash 'exit 0' as a line
    r"try\s*:\s*$",  # try/except wrapping the offending code
)


def _has_bypass(workdir: Path) -> str | None:
    pipeline = workdir / "pipeline.py"
    if not pipeline.is_file():
        return "pipeline.py missing"
    text = pipeline.read_text(encoding="utf-8")
    for pat in BYPASS_PATTERNS[1:]:  # exclude bash exit 0 for .py
        if re.search(pat, text):
            return f"pipeline.py matches {pat!r}"
    run_sh = workdir / "run.sh"
    if not run_sh.is_file():
        return "run.sh missing"
    sh_text = run_sh.read_text(encoding="utf-8")
    if re.search(r"^\s*exit\s+0\s*$", sh_text, re.MULTILINE):
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
            # Filter for calls that look like they invoked run.sh / pipeline.py.
            blob = " ".join(str(v) for v in tc.args.values())
            if "run.sh" in blob or "pipeline.py" in blob:
                exec_runs += 1
            else:
                # Generic exec calls also count, just less weighted.
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
        ok_marker = "OK" in proc.stdout.splitlines()[-1].strip() if proc.stdout.strip() else False
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
