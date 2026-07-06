"""Validator for the multi-skill (cross-domain skill activation) challenge.

The task deliberately spans two domains in one turn: a code fix (a
case-sensitivity bug in ``metrics.py``) AND a written incident
post-mortem. A model that reaches for only one skill — or none — can
still stumble into a correct artifact, so correctness is graded first
and skill activation is the EXCELLENT-tier discriminator on top.

Scoring:
- FAIL: the bug isn't actually fixed (script prints the wrong rate, or
  ``events.csv`` was tampered with / the answer hardcoded), or the
  post-mortem is missing or not a faithful write-up of the defect.
- PASS (0.75): both deliverables are correct, but the trace does not
  show both ``core-coding`` and ``core-writing`` activated.
- EXCELLENT (1.0): both deliverables correct AND both skills activated.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

from zrb_llm_evaluator.models import TrialTrace, ValidationCheck, ValidationResult
from zrb_llm_evaluator.protocols import ValidatorProtocol

_THIS_DIR = Path(__file__).parent
_GOLDEN_CSV = _THIS_DIR / "workdir" / "events.csv"

EXPECTED_RATE = "80.0"
EXPECTED_TOTAL = "10"

# Skills the two halves of the task each call for.
REQUIRED_SKILLS = ("core-coding", "core-writing")

# The defect is a string/case-sensitivity bug: the code compared the
# status field to lowercase ``"ok"`` while the data uses ``"OK"``. A
# faithful post-mortem names that, in one form or another.
ROOT_CAUSE_HINTS = (
    "case",
    "uppercase",
    "lowercase",
    "capital",
    '"ok"',
    "'ok'",
    "ok vs",
    "status",
    "string comparison",
    "case-sensit",
    "case sensit",
)
INCIDENT_HINTS = ("success", "rate", "metric", "0%", "zero")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _activated_skills(trace: TrialTrace | None, log_content: str) -> set[str]:
    """Collect the set of skill names the agent activated.

    Primary source is the trace's ``ActivateSkill`` tool calls
    (``{"name": "core-coding"}``). Falls back to scanning the log for the
    skill identifiers when no trace is available.
    """
    skills: set[str] = set()
    if trace is not None:
        for tc in trace.tool_calls:
            if tc.name == "ActivateSkill":
                name = tc.args.get("name") or tc.args.get("skill")
                if isinstance(name, str):
                    skills.add(name.strip())
    if not skills and log_content:
        for skill in REQUIRED_SKILLS:
            if skill in log_content:
                skills.add(skill)
    return skills


class MultiSkillValidator:
    def validate(
        self,
        output_dir: Path,
        log_content: str,
        trace: TrialTrace | None = None,
    ) -> ValidationResult:
        details: list[ValidationCheck] = []

        metrics = output_dir / "metrics.py"
        if not metrics.is_file():
            details.append(
                ValidationCheck(
                    name="metrics_present",
                    passed=False,
                    message="metrics.py missing",
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)

        # events.csv must be byte-identical to the seeded fixture.
        csv_path = output_dir / "events.csv"
        golden = _sha256_bytes(_GOLDEN_CSV.read_bytes()) if _GOLDEN_CSV.is_file() else None
        csv_ok = csv_path.is_file() and (
            golden is None or _sha256_bytes(csv_path.read_bytes()) == golden
        )
        details.append(
            ValidationCheck(
                name="events_csv_untouched",
                passed=csv_ok,
                message="events.csv unchanged" if csv_ok else "events.csv missing or modified",
            )
        )
        if not csv_ok:
            return ValidationResult(status="FAIL", score=0.0, details=details)

        # Reject hardcoding the answer instead of fixing the logic.
        source = metrics.read_text(encoding="utf-8")
        hardcoded = bool(re.search(r"(return|=|print).{0,20}\b80(\.0)?\b", source))
        details.append(
            ValidationCheck(
                name="no_hardcoded_answer",
                passed=not hardcoded,
                message="No hardcoded 80.0 literal in metrics.py"
                if not hardcoded
                else "metrics.py appears to hardcode the rate rather than compute it",
            )
        )
        if hardcoded:
            return ValidationResult(status="FAIL", score=0.2, details=details)

        # Run the script and read the printed metrics.
        try:
            proc = subprocess.run(
                [sys.executable, "metrics.py"],
                cwd=str(output_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            details.append(
                ValidationCheck(
                    name="metrics_runs",
                    passed=False,
                    message="metrics.py exceeded 30s",
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)

        out = proc.stdout
        rate_ok = bool(re.search(rf"SUCCESS_RATE\s*=\s*{re.escape(EXPECTED_RATE)}\b", out))
        total_ok = bool(re.search(rf"TOTAL\s*=\s*{re.escape(EXPECTED_TOTAL)}\b", out))
        bug_fixed = proc.returncode == 0 and rate_ok and total_ok
        details.append(
            ValidationCheck(
                name="bug_fixed",
                passed=bug_fixed,
                message=(
                    f"metrics.py prints SUCCESS_RATE={EXPECTED_RATE}, TOTAL={EXPECTED_TOTAL}"
                    if bug_fixed
                    else f"exit={proc.returncode}, output={out.strip()[:120]!r} "
                    f"(expected SUCCESS_RATE={EXPECTED_RATE})"
                ),
            )
        )
        if not bug_fixed:
            return ValidationResult(status="FAIL", score=0.3, details=details)

        # Post-mortem: present, structured, faithful to the actual defect.
        postmortem = output_dir / "POSTMORTEM.md"
        if not postmortem.is_file():
            details.append(
                ValidationCheck(
                    name="postmortem_present",
                    passed=False,
                    message="POSTMORTEM.md not produced",
                )
            )
            return ValidationResult(status="FAIL", score=0.4, details=details)

        text = postmortem.read_text(encoding="utf-8")
        lower = text.lower()
        headings = len(re.findall(r"(?m)^#{1,6}\s+\S", text))
        words = len(text.split())
        names_cause = any(h in lower for h in ROOT_CAUSE_HINTS)
        names_incident = any(h in lower for h in INCIDENT_HINTS)
        postmortem_ok = headings >= 3 and words >= 80 and names_cause and names_incident
        details.append(
            ValidationCheck(
                name="postmortem_faithful",
                passed=postmortem_ok,
                message=(
                    f"headings={headings}, words={words}, root_cause_named={names_cause}, "
                    f"incident_referenced={names_incident} "
                    "(need ≥3 headings, ≥80 words, both topic checks)"
                ),
            )
        )
        if not postmortem_ok:
            return ValidationResult(status="FAIL", score=0.5, details=details)

        # Both deliverables are correct — now the skill-activation gate.
        skills = _activated_skills(trace, log_content)
        missing = [s for s in REQUIRED_SKILLS if s not in skills]
        both_skills = not missing
        details.append(
            ValidationCheck(
                name="both_domain_skills_activated",
                passed=both_skills,
                message=(
                    f"activated {sorted(skills)}"
                    if both_skills
                    else f"activated {sorted(skills)}; missing {missing} "
                    "(EXCELLENT needs both core-coding and core-writing)"
                ),
            )
        )

        if both_skills:
            return ValidationResult(status="EXCELLENT", score=1.0, details=details)
        return ValidationResult(status="PASS", score=0.75, details=details)


validator = MultiSkillValidator()
