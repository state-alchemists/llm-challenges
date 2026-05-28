"""Validator for the copywriting (v1→v2 migration guide) challenge.

Replaces the loose keyword counters of the prior revision with structural
checks: ordered headings, code-block pairing near breaking-change mentions,
and a parsable checklist or upgrade command at the end. Pure-text models
can still pass — but stuffing "uuid bearer project_id /v2 completed" into
one paragraph will no longer score.
"""

from __future__ import annotations

import re
from pathlib import Path

from zrb_llm_evaluator.models import TrialTrace, ValidationCheck, ValidationResult
from zrb_llm_evaluator.protocols import ValidatorProtocol

MAX_SCORE = 8

# Each breaking-change topic the migration guide must cover, with the
# substrings (case-insensitive) that count as "this topic was mentioned"
# AND the constraint that at least one fenced code block must appear
# within CODE_PROXIMITY_LINES of the first mention.
BREAKING_CHANGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("auth_header", ("authorization", "bearer")),
    ("uuid_id", ("uuid",)),
    ("field_rename", ("completed", "done")),
    ("project_id_and_v2", ("project_id", "/v2")),
)
CODE_PROXIMITY_LINES = 8


def _find_migration_file(output_dir: Path) -> Path | None:
    primary = output_dir / "MIGRATION.md"
    if primary.is_file():
        return primary
    for entry in output_dir.iterdir():
        if entry.suffix.lower() == ".md" and "migration" in entry.name.lower():
            return entry
    return None


def _line_index(text: str) -> list[str]:
    return text.split("\n")


def _heading_positions(lines: list[str]) -> list[tuple[int, int, str]]:
    """Return [(line_no, level, text_lower), ...] for ATX-style headings."""
    out: list[tuple[int, int, str]] = []
    for i, raw in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.*)$", raw)
        if match:
            out.append((i, len(match.group(1)), match.group(2).strip().lower()))
    return out


def _code_block_starts(lines: list[str]) -> list[int]:
    """Return line numbers of opening fenced code blocks (toggling)."""
    starts: list[int] = []
    inside = False
    for i, raw in enumerate(lines):
        if re.match(r"^\s*```", raw):
            if not inside:
                starts.append(i)
            inside = not inside
    return starts


def _topic_has_proximate_code(
    lines: list[str], code_starts: list[int], needles: tuple[str, ...]
) -> tuple[bool, bool]:
    """Return (mentioned, has_proximate_code).

    A topic counts as "has proximate code" if *any* mention in the doc is
    within ``CODE_PROXIMITY_LINES`` of a fenced code block. The earlier
    revision locked onto the first mention, which penalized the common
    "summary table up top, detailed sections below with code" structure —
    the table row mentioned the topic but the matching code lived in a
    deeper section, beyond the proximity window.
    """
    needles_lower = [n.lower() for n in needles]
    mention_lines: list[int] = []

    # Strict pass: every needle present on the same line.
    for i, raw in enumerate(lines):
        lower = raw.lower()
        if all(needle in lower for needle in needles_lower):
            mention_lines.append(i)

    # Loose fallback for split-across-lines mentions: take the first
    # occurrence of each needle.
    if not mention_lines:
        for needle in needles_lower:
            for i, raw in enumerate(lines):
                if needle in raw.lower():
                    mention_lines.append(i)
                    break

    if not mention_lines:
        return False, False

    proximate = any(
        any(abs(start - mline) <= CODE_PROXIMITY_LINES for start in code_starts)
        for mline in mention_lines
    )
    return True, proximate


class CopywritingValidator:
    def validate(
        self,
        output_dir: Path,
        log_content: str,
        trace: TrialTrace | None = None,
    ) -> ValidationResult:
        details: list[ValidationCheck] = []
        migration = _find_migration_file(output_dir)
        if migration is None:
            details.append(
                ValidationCheck(
                    name="migration_file",
                    passed=False,
                    message="MIGRATION.md not found",
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)

        details.append(
            ValidationCheck(
                name="migration_file",
                passed=True,
                message=f"Using {migration.name}",
            )
        )

        content = migration.read_text(encoding="utf-8")
        lines = _line_index(content)
        score = 0

        headings = _heading_positions(lines)
        has_multi_level = (
            len({lvl for _, lvl, _ in headings}) >= 2 and len(headings) >= 3
        )
        score += int(has_multi_level)
        details.append(
            ValidationCheck(
                name="structured_headings",
                passed=has_multi_level,
                message=f"{len(headings)} heading(s) across "
                f"{len({lvl for _, lvl, _ in headings})} level(s) "
                "(need ≥3 headings, ≥2 levels)",
            )
        )

        word_count = len(content.split())
        long_enough = word_count >= 400
        score += int(long_enough)
        details.append(
            ValidationCheck(
                name="substantial_content",
                passed=long_enough,
                message=f"{word_count} words (need ≥400)",
            )
        )

        code_starts = _code_block_starts(lines)
        enough_blocks = len(code_starts) >= 3
        score += int(enough_blocks)
        details.append(
            ValidationCheck(
                name="code_blocks",
                passed=enough_blocks,
                message=f"{len(code_starts)} fenced code block(s) (need ≥3)",
            )
        )

        # Each breaking change must be mentioned AND have a code block nearby.
        # One point per topic — all 4 must pass to fully clear this section.
        # (Earlier revision awarded a coarse 0/1/2-point bonus that capped the
        # achievable score at 6/8, making EXCELLENT mathematically unreachable.)
        for topic, needles in BREAKING_CHANGES:
            mentioned, proximate = _topic_has_proximate_code(
                lines, code_starts, needles
            )
            ok = mentioned and proximate
            details.append(
                ValidationCheck(
                    name=f"topic_{topic}",
                    passed=ok,
                    message=(
                        f"mentioned + code within {CODE_PROXIMITY_LINES} lines"
                        if ok
                        else "missing or not paired with nearby code block"
                    ),
                )
            )
            if ok:
                score += 1

        # Checklist (markdown list with leading "- [ ]" or numbered) AND an
        # explicit upgrade command in a code block. Both must be present and
        # in the final third of the document to count.
        final_third_start = max(1, len(lines) * 2 // 3)
        tail = "\n".join(lines[final_third_start:])
        has_checklist = bool(
            re.search(r"^\s*-\s*\[", tail, re.MULTILINE)
            or re.search(r"^\s*\d+\.\s", tail, re.MULTILINE)
        )
        # Recognize the common upgrade-command variants developers actually use:
        # explicit --upgrade/-U flags, `pip upgrade`, `pipx install/upgrade`,
        # `uv pip install`, `poetry add/update`, and the very common
        # `pip install <pkg><version-constraint>` (e.g. `>=`, `~=`, `==`) which
        # is the canonical "upgrade to at-least-N" pattern in Python.
        has_upgrade = bool(
            re.search(
                r"pip\s+install\s+(?:--upgrade|-U)\b"
                r"|pip\s+upgrade\b"
                r"|pip\s+install\s+\S+\s*[><~=]=?"
                r"|pipx\s+(?:install|upgrade)\b"
                r"|uv\s+pip\s+install\b"
                r"|poetry\s+(?:add|update)\b",
                tail,
                re.IGNORECASE,
            )
        )
        finish_ok = has_checklist and has_upgrade
        score += int(finish_ok)
        details.append(
            ValidationCheck(
                name="checklist_and_upgrade_at_end",
                passed=finish_ok,
                message=(
                    f"checklist={has_checklist}, upgrade_cmd={has_upgrade} "
                    "(both required, in the final third of the doc)"
                ),
            )
        )

        normalized = score / MAX_SCORE
        if score >= 7:
            status = "EXCELLENT"
        elif score >= 5:
            status = "PASS"
        else:
            status = "FAIL"
        return ValidationResult(status=status, score=normalized, details=details)


validator = CopywritingValidator()
