"""Validator for the delegate-audit (parallel delegation) challenge.

Six independent modules each hide a distinct defect; the agent must
produce one faithful written finding per module. The task is a natural
fan-out — the modules share no state — so a model that recognizes the
opportunity can delegate the six audits to subagents and run them in
parallel. Delegation is NOT required to pass: correctness of the six
findings is graded first, and observed delegation is the EXCELLENT-tier
discriminator on top. Grading it as a bonus (never a gate) keeps a model
that delegates badly from outscoring one that audits well solo.

Scoring:
- FAIL: fewer than all six modules have a faithful finding
  (score = covered / 6).
- PASS (0.8): all six findings are faithful, but the trace shows no
  parallel delegation.
- EXCELLENT (1.0): all six findings faithful AND the trace shows the
  agent fanned the work out to subagents (≥2 delegate calls).
"""

from __future__ import annotations

from pathlib import Path

from zrb_llm_evaluator.models import TrialTrace, ValidationCheck, ValidationResult
from zrb_llm_evaluator.protocols import ValidatorProtocol

# (module stem, human filename, accepted issue-keyword substrings). A
# finding counts as faithful when a produced markdown file references the
# module AND names its specific problem via one of these substrings.
MODULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "credentials",
        "credentials.py",
        ("password", "hardcoded", "hard-coded", "hard coded", "secret",
         "credential", "api key", "api_key", "apikey", "plaintext"),
    ),
    (
        "evaluator",
        "evaluator.py",
        ("eval", "injection", "arbitrary code", "code execution", "exec",
         "rce", "untrusted", "sandbox"),
    ),
    (
        "cache",
        "cache.py",
        ("unbounded", "evict", "eviction", "memory", "leak", "no limit",
         "grows", "grow", "ttl", "expire", "expiry", "bounded"),
    ),
    (
        "fetcher",
        "fetcher.py",
        ("timeout", "hang", "block", "ssrf", "indefinit"),
    ),
    (
        "stats",
        "stats.py",
        ("integer division", "floor division", "//", "truncat", "integer",
         "int division", "rounds down", "round down", "floor"),
    ),
    (
        "logger",
        "logger.py",
        ("sensitive", "plaintext", "plain text", "pii", "redact", "password",
         "secret", "leak", "mask"),
    ),
)

# Delegation tool-name substring. Matches both zrb delegation tools —
# ``DelegateToAgent`` (blocking) and ``DelegateToAgentBackground`` (async)
# — and deliberately NOT ``GetDelegationResult`` ("delegation" doesn't
# contain the substring "delegate"), which only fetches a prior result
# and is not itself an act of delegation.
DELEGATE_HINT = "delegate"
# The runner may echo a done-marker; ignore obvious non-report files.
SKIP_MD_NAMES = {"readme.md", "instruction.md"}
DELEGATE_THRESHOLD = 2


def _report_files(output_dir: Path) -> list[Path]:
    return [
        p
        for p in output_dir.rglob("*.md")
        if p.is_file() and p.name.lower() not in SKIP_MD_NAMES
    ]


def _module_covered(reports: list[tuple[str, str]], stem: str, filename: str,
                    keywords: tuple[str, ...]) -> bool:
    """A module is covered when some report references it (by module name or
    filename) AND names its specific defect via a keyword."""
    for name_lower, text in reports:
        references = stem in name_lower or stem in text or filename in text
        if references and any(k in text for k in keywords):
            return True
    return False


def _delegation_count(trace: TrialTrace | None, log_content: str) -> int:
    """Count delegated *tasks*, not delegate tool calls.

    zrb's ``DelegateToAgent``/``DelegateToAgentBackground`` fan out in a
    single call via ``tasks=[{...}, ...]`` — the recommended way to run
    several sub-agents concurrently. Counting calls would score that ideal
    one-call fan-out the same as one delegation, so we sum the ``tasks``
    list length (falling back to 1 for a single flat delegation).
    """
    if trace is not None:
        total = 0
        saw_delegate = False
        for tc in trace.tool_calls:
            if DELEGATE_HINT not in tc.name.lower():
                continue
            saw_delegate = True
            tasks = tc.args.get("tasks")
            if isinstance(tasks, list) and tasks:
                total += len(tasks)
            else:
                total += 1
        if saw_delegate:
            return total
    # Fallback: count delegate tool-call mentions in the log. This can't
    # see fan-out task counts, so it's a floor, not an exact tally.
    return log_content.count("DelegateToAgent")


class DelegateAuditValidator:
    def validate(
        self,
        output_dir: Path,
        log_content: str,
        trace: TrialTrace | None = None,
    ) -> ValidationResult:
        details: list[ValidationCheck] = []

        raw_reports = _report_files(output_dir)
        # Pre-read each report once as (filename_lower, content_lower).
        reports: list[tuple[str, str]] = []
        for p in raw_reports:
            try:
                reports.append((p.name.lower(), p.read_text(encoding="utf-8", errors="ignore").lower()))
            except OSError:
                continue

        details.append(
            ValidationCheck(
                name="findings_files_present",
                passed=len(raw_reports) >= len(MODULES),
                message=f"{len(raw_reports)} markdown finding file(s) produced "
                f"(expected ≥{len(MODULES)})",
            )
        )

        covered = 0
        for stem, filename, keywords in MODULES:
            ok = _module_covered(reports, stem, filename, keywords)
            if ok:
                covered += 1
            details.append(
                ValidationCheck(
                    name=f"audit_{stem}",
                    passed=ok,
                    message=(
                        f"{filename}: defect identified in a finding"
                        if ok
                        else f"{filename}: no faithful finding (module + specific issue) found"
                    ),
                )
            )

        all_covered = covered == len(MODULES)

        n_deleg = _delegation_count(trace, log_content)
        delegated = n_deleg >= DELEGATE_THRESHOLD
        details.append(
            ValidationCheck(
                name="delegated_to_subagents",
                passed=delegated,
                message=(
                    f"{n_deleg} sub-agent task(s) delegated "
                    f"(EXCELLENT needs ≥{DELEGATE_THRESHOLD}; correctness alone still PASSes)"
                ),
            )
        )

        if not all_covered:
            return ValidationResult(
                status="FAIL",
                score=round(covered / len(MODULES), 3),
                details=details,
            )
        if delegated:
            return ValidationResult(status="EXCELLENT", score=1.0, details=details)
        return ValidationResult(status="PASS", score=0.8, details=details)


validator = DelegateAuditValidator()
