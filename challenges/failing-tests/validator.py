"""Validator for the failing-tests challenge (SWE-bench-style).

The contract:
- Stage a fresh copy of every test file from this directory's golden
  ``tests/`` (stored alongside the validator) and assert byte-equality
  with what the agent has in its workdir — any divergence means the
  agent edited the tests, which is a hard FAIL.
- Then run ``pytest -q`` in a subprocess; ALL tests must pass. The
  interpreter is resolved by ``_resolve_pytest_cmd`` rather than assumed to
  be ``sys.executable`` — the evaluator often runs from a pipx venv with no
  pytest installed, which would fail every trial regardless of the agent's
  work. If no interpreter with pytest exists, the ``pytest_available`` check
  reports it as a harness error so it is never misread as a model failure.
- Inspect the source under ``src/`` for ``pytest.skip``, ``xfail``, or
  similar bypass markers and FAIL if any are introduced.

This is a strict pass/fail benchmark by design — the suite either runs
clean or the agent didn't fix the bugs.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
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


def _probe(cmd: list[str], cwd: Path) -> bool:
    """True if ``cmd`` exits 0 when run from ``cwd``.

    Always probed from the cwd the suite will run in: version-manager shims
    (pyenv, asdf) resolve to a different interpreter per directory, so a shim
    that works here may resolve to a pytest-less python inside the workdir.
    """
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _has_pytest(python: str, cwd: Path) -> bool:
    """True if ``python`` can import pytest when run from ``cwd``."""
    return _probe([python, "-c", "import pytest"], cwd)


def _resolve_pytest_cmd(output_dir: Path) -> list[str] | None:
    """Find a runnable pytest, or None if the host has none.

    ``sys.executable`` is whatever interpreter the evaluator itself runs
    under (e.g. a pipx venv), which frequently has no pytest installed —
    so it is a candidate, not the answer. Candidates are tried in order of
    how closely they match the environment the agent itself used, and every
    candidate is probed before use rather than assumed:

    1. a virtualenv the agent created inside its workdir
    2. ``$PYTEST_PYTHON`` / ``$FAILING_TESTS_PYTHON`` override
    3. the evaluator's own interpreter
    4. plain ``python3`` / ``python`` from PATH
    5. ``pytest`` as a console script on PATH
    """
    cwd = output_dir if output_dir.is_dir() else Path.cwd()

    for venv in (".venv", "venv", "env"):
        candidate = output_dir / venv / ("Scripts" if os.name == "nt" else "bin") / "python"
        if candidate.is_file() and _has_pytest(str(candidate), cwd):
            return [str(candidate), "-m", "pytest"]

    for env_var in ("PYTEST_PYTHON", "FAILING_TESTS_PYTHON"):
        override = os.environ.get(env_var)
        if override and _has_pytest(override, cwd):
            return [override, "-m", "pytest"]

    seen = {sys.executable}
    if _has_pytest(sys.executable, cwd):
        return [sys.executable, "-m", "pytest"]

    # Prefer a concrete interpreter over the bare console script: `-m pytest`
    # pins which python runs the suite, while a shim can silently switch.
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found and found not in seen:
            seen.add(found)
            if _has_pytest(found, cwd):
                return [found, "-m", "pytest"]

    console_script = shutil.which("pytest")
    if console_script and _probe([console_script, "--version"], cwd):
        return [console_script]

    return None


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

        pytest_cmd = _resolve_pytest_cmd(output_dir)
        if pytest_cmd is None:
            details.append(
                ValidationCheck(
                    name="pytest_available",
                    passed=False,
                    message=(
                        "HARNESS ENVIRONMENT ERROR — not a model failure. No "
                        "interpreter with pytest was found, so the agent's fix "
                        f"was never executed. Tried: {sys.executable}, a venv in "
                        "the workdir, $PYTEST_PYTHON, and python3/python on "
                        "PATH. Install pytest into the evaluator's environment "
                        "or set $PYTEST_PYTHON, then re-run this test case."
                    ),
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)
        details.append(
            ValidationCheck(
                name="pytest_available",
                passed=True,
                message=f"Using {' '.join(pytest_cmd)}",
            )
        )

        try:
            proc = subprocess.run(
                [*pytest_cmd, "-q", "--tb=short"],
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
