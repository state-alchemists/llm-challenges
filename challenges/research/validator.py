"""Validator for the architecture-decision-record (research) challenge.

Replaces pure keyword counting with structural ADR checks: the canonical
section names must appear as headings in the canonical order, the
Decision section must call out a specific option, and pros/cons must
appear inside Consequences/Alternatives rather than as bare words.
"""

from __future__ import annotations

import re
from pathlib import Path

from zrb_llm_evaluator.models import TrialTrace, ValidationCheck, ValidationResult
from zrb_llm_evaluator.protocols import ValidatorProtocol

MAX_SCORE = 8
SKIP_FILES = {"readme.md", "system_context.md"}

CANONICAL_SECTIONS: tuple[str, ...] = (
    "context",
    "decision",
    "consequences",
    "alternatives",
)


def _find_adr_file(output_dir: Path) -> Path | None:
    primary = output_dir / "ADR-001-notification-architecture.md"
    if primary.is_file():
        return primary
    candidates = sorted(
        entry
        for entry in output_dir.iterdir()
        if entry.suffix.lower() == ".md" and entry.name.lower() not in SKIP_FILES
    )
    return candidates[0] if candidates else None


def _heading_sections(content: str) -> list[tuple[int, int, str]]:
    """Return [(line_no, level, heading_text_lower), ...] for all ATX headings."""
    out: list[tuple[int, int, str]] = []
    for i, raw in enumerate(content.split("\n")):
        match = re.match(r"^(#{1,6})\s+(.*)$", raw)
        if match:
            out.append((i, len(match.group(1)), match.group(2).strip().lower()))
    return out


def _section_body(content: str, heading_lower: str) -> str:
    """Return the body text between a heading matching ``heading_lower`` and the
    next heading of equal-or-higher level (i.e., subheadings stay in scope)."""
    lines = content.split("\n")
    headings = _heading_sections(content)
    for idx, (line_no, level, text) in enumerate(headings):
        if heading_lower in text:
            start = line_no + 1
            end = len(lines)
            for next_line, next_level, _ in headings[idx + 1 :]:
                if next_level <= level:
                    end = next_line
                    break
            return "\n".join(lines[start:end])
    return ""


class ResearchValidator:
    def validate(
        self,
        output_dir: Path,
        log_content: str,
        trace: TrialTrace | None = None,
    ) -> ValidationResult:
        details: list[ValidationCheck] = []
        adr = _find_adr_file(output_dir)
        if adr is None:
            details.append(
                ValidationCheck(
                    name="adr_file",
                    passed=False,
                    message="No ADR markdown file found",
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)

        details.append(
            ValidationCheck(
                name="adr_file",
                passed=True,
                message=f"Using {adr.name}",
            )
        )

        content = adr.read_text(encoding="utf-8")
        lower = content.lower()
        headings = _heading_sections(content)
        score = 0

        words = len(content.split())
        long_enough = words >= 500
        score += int(long_enough)
        details.append(
            ValidationCheck(
                name="substantial_content",
                passed=long_enough,
                message=f"{words} words (need ≥500)",
            )
        )

        # Canonical sections must appear as headings (not just inline words)
        # AND in canonical order.
        section_positions: dict[str, int] = {}
        for line_no, _level, text in headings:
            for section in CANONICAL_SECTIONS:
                if section in text and section not in section_positions:
                    section_positions[section] = line_no
        found_sections = list(section_positions.keys())
        ordered_canonical = [s for s in CANONICAL_SECTIONS if s in section_positions]
        ordered_actual = sorted(
            ordered_canonical, key=lambda s: section_positions[s]
        )
        ordered_ok = (
            len(found_sections) >= 3 and ordered_actual == ordered_canonical
        )
        score += int(ordered_ok)
        details.append(
            ValidationCheck(
                name="canonical_sections_as_ordered_headings",
                passed=ordered_ok,
                message=(
                    f"found {found_sections} as headings in canonical order"
                    if ordered_ok
                    else f"found {found_sections}; missing or out-of-order"
                ),
            )
        )

        # Tolerate any bolding/spacing around the label and value, e.g.
        # `**Status:** Proposed`, `Status - Accepted`, `**Status**: **Draft**`.
        status_ok = bool(
            re.search(
                r"(?im)^\**\s*status\s*\**\s*[:\-]?\s*\**\s*(proposed|accepted|draft)\s*\**\s*$",
                content,
            )
        )
        score += int(status_ok)
        details.append(
            ValidationCheck(
                name="status_field",
                passed=status_ok,
                message="Status: Proposed/Accepted/Draft line present"
                if status_ok
                else "Missing explicit Status: <value> line",
            )
        )

        has_kafka = "kafka" in lower
        has_redis = "redis" in lower
        both_ok = has_kafka and has_redis
        score += int(both_ok)
        details.append(
            ValidationCheck(
                name="evaluates_both_options",
                passed=both_ok,
                message=f"kafka={has_kafka}, redis={has_redis}",
            )
        )

        # Decision section must contain a definitive choice — either Kafka or
        # Redis named in a committing phrase, *inside the Decision section*.
        decision_body = _section_body(content, "decision")
        decision_lower = decision_body.lower()
        # Phrase-specific commit detection: a generic verb adjacent to the
        # chosen option, OR a colon-style declaration. Phrase-specificity
        # avoids dual-true when the rejected option is also mentioned for
        # contrast within the Decision section.
        commit_verbs = ("use", "adopt", "choose", "select", "recommend", "go with")

        def _commits_to(option: str) -> bool:
            if option not in decision_lower:
                return False
            for verb in commit_verbs:
                if re.search(rf"\b{verb}\b[^.\n]{{0,40}}\b{option}\b", decision_lower):
                    return True
                if re.search(rf"\bwe\s+will\s+{verb}\b[^.\n]{{0,40}}\b{option}\b", decision_lower):
                    return True
            if re.search(rf"\b(decision|chosen|recommendation)\s*[:=]\s*[^.\n]*\b{option}\b", decision_lower):
                return True
            return False

        commits_to_kafka = _commits_to("kafka")
        commits_to_redis = _commits_to("redis")
        recommendation_ok = bool(decision_body) and (
            commits_to_kafka != commits_to_redis  # exactly one
        )
        score += int(recommendation_ok)
        details.append(
            ValidationCheck(
                name="definitive_decision_in_decision_section",
                passed=recommendation_ok,
                message=(
                    "Decision section names exactly one option with a commit phrase"
                    if recommendation_ok
                    else "Decision section missing, ambiguous, or commits to both/neither"
                ),
            )
        )

        tech_terms = (
            "throughput",
            "ordering",
            "retention",
            "consumer group",
            "exactly-once",
            "at-least-once",
            "operational",
            "replication",
            "partition",
            "stream",
            "durability",
            "latency",
        )
        covered_tech = [t for t in tech_terms if t in lower]
        tech_ok = len(covered_tech) >= 4
        score += int(tech_ok)
        details.append(
            ValidationCheck(
                name="technical_properties",
                passed=tech_ok,
                message=f"covered {len(covered_tech)}/12 ({', '.join(covered_tech[:4])}...)",
            )
        )

        # Consequences section must contain BOTH pros and cons language.
        consequences_body = _section_body(content, "consequences").lower()
        has_pros = any(
            t in consequences_body for t in ("pro", "advantage", "benefit", "positive")
        )
        has_cons = any(
            t in consequences_body
            for t in ("con", "disadvantage", "downside", "risk", "negative", "trade-off", "tradeoff")
        )
        pros_cons_ok = bool(consequences_body) and has_pros and has_cons
        score += int(pros_cons_ok)
        details.append(
            ValidationCheck(
                name="pros_and_cons_in_consequences",
                passed=pros_cons_ok,
                message=f"in Consequences: pros={has_pros}, cons={has_cons}",
            )
        )

        # Alternatives section must mention the rejected option.
        alternatives_body = _section_body(content, "alternatives").lower()
        if commits_to_kafka:
            rejected = "redis"
        elif commits_to_redis:
            rejected = "kafka"
        else:
            rejected = ""
        alternatives_ok = bool(alternatives_body) and (
            rejected in alternatives_body if rejected else True
        )
        score += int(alternatives_ok)
        details.append(
            ValidationCheck(
                name="alternatives_discusses_rejected_option",
                passed=alternatives_ok,
                message=(
                    f"Alternatives section discusses {rejected}"
                    if alternatives_ok and rejected
                    else "Alternatives section missing or omits the rejected option"
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


validator = ResearchValidator()
