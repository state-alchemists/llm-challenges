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

# Sections recognized as structural markers. ``title``/``status`` are not
# scored for ordering but must be recognized so their bodies can be read and
# so they are not mistaken for one of the canonical four.
KNOWN_SECTIONS: tuple[str, ...] = (*CANONICAL_SECTIONS, "title", "status")

# A bold run alone on its line — ``**Decision**`` / ``- **Decision:**``.
# Requires end-of-line after the bold so that a bullet with a bold lead-in
# (``* **Reduced overhead**: leverages ...``) is NOT treated as a heading.
_BOLD_HEADING_RE = re.compile(r"^\s*(?:[-*+]\s+)?\*\*([^*]+)\*\*\s*:?\s*$")

# ``Decision:`` or ``Decision: Redis Streams`` — a short capitalized label
# followed by a colon. Only kept if the label names a KNOWN_SECTION, which is
# what stops ``Pros:``/``Cons:`` inside Consequences from splitting the body.
_LABEL_HEADING_RE = re.compile(r"^\s*(?:[-*+]\s+)?\**([A-Za-z][A-Za-z /&-]{0,40}?)\**\s*:")

# Synthetic depth for non-ATX section markers: shallow enough that the next
# marker closes the previous section, deep enough to sit under an H1 title.
_PSEUDO_LEVEL = 2

# Phrases that mark an option as being weighed against or discarded rather
# than adopted. Spaces are load-bearing: " over " must not fire on
# "overhead"/"overall", and "not " must not fire on "noting".
CONTRAST_MARKERS: tuple[str, ...] = (
    "compared to",
    "comparison to",
    "rather than",
    "instead of",
    "as opposed to",
    "opposed to",
    "versus",
    " vs ",
    " vs.",
    "unlike",
    " over ",
    "not ",
    "avoid",
    "reject",
    "forgo",
    "forego",
    "against",
    "away from",
    "dismiss",
    "ruled out",
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


def _section_label(text: str) -> str | None:
    """Canonical ADR section a heading names, or None if it names none.

    Matches on the *leading* words rather than a substring anywhere in the
    text, so a title like ``# ADR-001: Notification Architecture Decision``
    is not mistaken for the Decision section.
    """
    stripped = text.strip()
    stripped = re.sub(r"^[-*+]\s+", "", stripped)  # list bullet
    stripped = re.sub(r"^\d+[.)]\s*", "", stripped)  # "1. Context"
    stripped = stripped.strip(" *_`")
    stripped = stripped.rstrip(":").strip(" *_`").lower()
    for section in KNOWN_SECTIONS:
        if (
            stripped == section
            or stripped.startswith(section + " ")  # "alternatives considered"
            or stripped.startswith(section + ":")  # "decision: redis streams"
        ):
            return section
    return None


def _heading_sections(content: str) -> list[tuple[int, int, str, str | None]]:
    """Return [(line_no, level, heading_text_lower, section_label), ...].

    ATX headings (``## Context``) are always returned. Because the instruction
    describes the required structure as a bold bullet list and never mandates
    markdown headings, two further conventions count as section markers:
    a bold run alone on its line (``**Context**``) and a plain label
    (``Context:``). Those two are only honored when they name a
    KNOWN_SECTION — otherwise ``Pros:``/``Cons:`` inside Consequences would
    split that section and hide its body.
    """
    out: list[tuple[int, int, str, str | None]] = []
    for i, raw in enumerate(content.split("\n")):
        atx = re.match(r"^(#{1,6})\s+(.*)$", raw)
        if atx:
            text = atx.group(2).strip().lower()
            out.append((i, len(atx.group(1)), text, _section_label(text)))
            continue
        for pattern in (_BOLD_HEADING_RE, _LABEL_HEADING_RE):
            match = pattern.match(raw)
            if not match:
                continue
            label = _section_label(match.group(1))
            if label is not None:
                out.append((i, _PSEUDO_LEVEL, raw.strip().lower(), label))
                break
    return out


def _section_body(content: str, section: str) -> str:
    """Return the body text under the first heading naming ``section``, up to
    the next heading of equal-or-higher level (subheadings stay in scope)."""
    lines = content.split("\n")
    headings = _heading_sections(content)
    for idx, (line_no, level, _text, label) in enumerate(headings):
        if label != section:
            continue
        start = line_no + 1
        end = len(lines)
        for next_line, next_level, _next_text, _next_label in headings[idx + 1 :]:
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
        for line_no, _level, _text, label in headings:
            if label in CANONICAL_SECTIONS and label not in section_positions:
                section_positions[label] = line_no
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
                r"(?im)^\s*(?:[-*+]\s+)?\**\s*status\s*\**\s*[:\-]?\s*\**\s*"
                r"(proposed|accepted|draft)\s*\**\s*$",
                content,
            )
        )
        if not status_ok:
            # Also accept the value on its own line under a Status heading —
            # `## Status\nProposed` is standard ADR form, and the instruction
            # only asks for a Status section, not a single-line field.
            status_body = _section_body(content, "status")
            first_line = next(
                (l.strip().strip("*_` ") for l in status_body.split("\n") if l.strip()),
                "",
            )
            status_ok = bool(
                re.fullmatch(r"(?i)(proposed|accepted|draft)\s*\.?", first_line)
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
        # contrast within the Decision section — the `[^.\n]{0,40}` window
        # cannot cross a sentence boundary, which is what keeps a contrastive
        # mention of the rejected option from also scoring as a commitment.
        # Verbs are inflected: "we will implement X using Redis" is every bit
        # as definitive as "we use Redis", so the stems must match their
        # -s/-ed/-ing forms rather than the bare infinitive only.
        commit_verbs = (
            r"us(?:e|es|ed|ing)",
            r"adopt(?:s|ed|ing)?",
            r"choos(?:e|es|ing)|chose|chosen",
            r"select(?:s|ed|ing)?",
            r"recommend(?:s|ed|ing)?",
            r"implement(?:s|ed|ing)?",
            r"go(?:es|ing)?\s+with|went\s+with",
            r"opt(?:s|ed|ing)?\s+for",
            r"standardiz(?:e|es|ed|ing)\s+on",
            r"proceed(?:s|ed|ing)?\s+with",
            r"settl(?:e|es|ed|ing)\s+on",
            r"migrat(?:e|es|ed|ing)\s+to",
            r"build(?:s|ing)?\s+on|built\s+on",
        )

        def _commits_to(option: str) -> bool:
            if option not in decision_lower:
                return False
            for verb in commit_verbs:
                pattern = rf"\b(?:{verb})\b([^.\n]{{0,40}}?)\b{option}\b"
                for match in re.finditer(pattern, decision_lower):
                    # A contrastive frame means the option is being rejected,
                    # not chosen — "compared to adopting Kafka", "use Redis
                    # over Kafka". Check both the span between verb and option
                    # and a short lead-in before the verb. Every match is
                    # examined, since one mention may be contrastive while
                    # another in the same section is a genuine commitment.
                    between = match.group(1)
                    lead_in = decision_lower[max(0, match.start() - 40) : match.start()]
                    if any(c in between or c in lead_in for c in CONTRAST_MARKERS):
                        continue
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
        if not alternatives_body:
            alternatives_msg = "Alternatives section missing"
        elif not rejected:
            # No option was identified as chosen, so there is no rejected one to
            # look for — say so rather than claiming the section omits it.
            alternatives_msg = (
                "Alternatives section present; no rejected option to check "
                "(Decision section named no single choice)"
            )
        elif alternatives_ok:
            alternatives_msg = f"Alternatives section discusses {rejected}"
        else:
            alternatives_msg = f"Alternatives section omits the rejected option ({rejected})"
        score += int(alternatives_ok)
        details.append(
            ValidationCheck(
                name="alternatives_discusses_rejected_option",
                passed=alternatives_ok,
                message=alternatives_msg,
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
