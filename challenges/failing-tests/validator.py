"""Validator for the failing-tests challenge (SWE-bench-style).

The contract:
- Stage a fresh copy of every test file from this directory's golden
  ``tests/`` (stored alongside the validator) and assert byte-equality
  with what the agent has in its workdir — any divergence means the
  agent edited the tests, which is a hard FAIL.
- Then run ``pytest -q`` in a subprocess; ALL tests must pass.
- Inspect the source under ``src/`` for ``pytest.skip``, ``xfail``, or
  similar bypass markers and FAIL if any are introduced.

This is a strict pass/fail benchmark by design — the suite either runs
clean or the agent didn't fix the bugs.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

from zrb_llm_evaluator.models import TrialTrace, ValidationCheck, ValidationResult
from zrb_llm_evaluator.protocols import ValidatorProtocol

# Golden hashes — recomputed at validator-load time from the source tree
# under this challenge's workdir/tests/. The runner stages workdir/ into
# the trial cwd, so the agent's tests/ must still match what we ship.
_THIS_DIR = Path(__file__).parent
_GOLDEN_TESTS_DIR = _THIS_DIR / "workdir" / "tests"
BYPASS_PATTERNS = (
    r"pytest\.skip\s*\(",
    r"pytest\.xfail\s*\(",
    r"@pytest\.mark\.skip",
    r"@pytest\.mark\.xfail",
    r"@pytest\.mark\.skipif",
    r"@unittest\.skip",
)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _golden_test_hashes() -> dict[str, str]:
    if not _GOLDEN_TESTS_DIR.is_dir():
        return {}
    out: dict[str, str] = {}
    for path in sorted(_GOLDEN_TESTS_DIR.rglob("*.py")):
        rel = path.relative_to(_GOLDEN_TESTS_DIR).as_posix()
        out[rel] = _sha256(path)
    return out


def _scan_for_bypass(root: Path) -> list[str]:
    hits: list[str] = []
    for p in root.rglob("*.py"):
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pat in BYPASS_PATTERNS:
            if re.search(pat, text):
                hits.append(f"{p.relative_to(root).as_posix()}: matches {pat!r}")
                break
    return hits


class FailingTestsValidator:
    def validate(
        self,
        output_dir: Path,
        log_content: str,
        trace: TrialTrace | None = None,
    ) -> ValidationResult:
        details: list[ValidationCheck] = []

        tests_dir = output_dir / "tests"
        if not tests_dir.is_dir():
            details.append(
                ValidationCheck(
                    name="tests_dir_present",
                    passed=False,
                    message="tests/ directory missing from output",
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)

        golden = _golden_test_hashes()
        agent_hashes: dict[str, str] = {}
        for path in tests_dir.rglob("*.py"):
            rel = path.relative_to(tests_dir).as_posix()
            agent_hashes[rel] = _sha256(path)

        missing = [name for name in golden if name not in agent_hashes]
        modified = [
            name
            for name, h in golden.items()
            if name in agent_hashes and agent_hashes[name] != h
        ]
        if missing or modified:
            details.append(
                ValidationCheck(
                    name="tests_untouched",
                    passed=False,
                    message=(
                        f"Test files were modified or removed — "
                        f"missing={missing} modified={modified}. "
                        "The instruction explicitly forbids changing tests/."
                    ),
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)
        details.append(
            ValidationCheck(
                name="tests_untouched",
                passed=True,
                message=f"{len(golden)} test file(s) byte-identical to golden",
            )
        )

        bypass_hits = _scan_for_bypass(output_dir)
        if bypass_hits:
            details.append(
                ValidationCheck(
                    name="no_test_bypass",
                    passed=False,
                    message="Found pytest skip/xfail markers: " + "; ".join(bypass_hits),
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)
        details.append(
            ValidationCheck(
                name="no_test_bypass",
                passed=True,
                message="No skip/xfail markers introduced",
            )
        )

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--tb=short"],
                cwd=str(output_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            details.append(
                ValidationCheck(
                    name="pytest_run",
                    passed=False,
                    message="pytest exceeded 120s — likely an infinite loop in the fix",
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)

        passed = proc.returncode == 0
        summary_line = ""
        for line in (proc.stdout + proc.stderr).splitlines()[::-1]:
            if "passed" in line or "failed" in line or "error" in line:
                summary_line = line.strip()
                break
        details.append(
            ValidationCheck(
                name="pytest_run",
                passed=passed,
                message=(
                    summary_line
                    or (f"exit={proc.returncode}, stderr={proc.stderr[:300]}")
                ),
            )
        )

        if not passed:
            return ValidationResult(status="FAIL", score=0.0, details=details)

        return ValidationResult(status="EXCELLENT", score=1.0, details=details)


validator = FailingTestsValidator()
