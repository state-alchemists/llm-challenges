"""Validator for the big-haystack long-context retrieval challenge.

The agent must produce `answer.txt` with two lines: order_id and customer.
Both must match the canonical values exactly. No partial credit for
"close enough" — needle-in-haystack tasks are binary by nature.
"""

from __future__ import annotations

from pathlib import Path

from zrb_llm_evaluator.models import TrialTrace, ValidationCheck, ValidationResult
from zrb_llm_evaluator.protocols import ValidatorProtocol

EXPECTED_ORDER_ID = "42-X9Q"
EXPECTED_CUSTOMER = "alice@example.com"


class BigHaystackValidator:
    def validate(
        self,
        output_dir: Path,
        log_content: str,
        trace: TrialTrace | None = None,
    ) -> ValidationResult:
        details: list[ValidationCheck] = []

        answer = output_dir / "answer.txt"
        if not answer.is_file():
            details.append(
                ValidationCheck(
                    name="answer_file_present",
                    passed=False,
                    message="answer.txt not produced",
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)

        text = answer.read_text(encoding="utf-8", errors="replace").strip()
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        details.append(
            ValidationCheck(
                name="answer_file_present",
                passed=True,
                message=f"answer.txt has {len(lines)} non-empty line(s)",
            )
        )

        order_line = next((ln for ln in lines if ln.lower().startswith("order_id=")), "")
        customer_line = next((ln for ln in lines if ln.lower().startswith("customer=")), "")

        order_val = order_line.split("=", 1)[1] if "=" in order_line else ""
        customer_val = customer_line.split("=", 1)[1] if "=" in customer_line else ""

        order_ok = order_val == EXPECTED_ORDER_ID
        customer_ok = customer_val == EXPECTED_CUSTOMER

        details.append(
            ValidationCheck(
                name="order_id_correct",
                passed=order_ok,
                message=(
                    f"order_id={order_val!r}"
                    if order_ok
                    else f"got {order_val!r}, expected {EXPECTED_ORDER_ID!r}"
                ),
            )
        )
        details.append(
            ValidationCheck(
                name="customer_correct",
                passed=customer_ok,
                message=(
                    f"customer={customer_val!r}"
                    if customer_ok
                    else f"got {customer_val!r}, expected {EXPECTED_CUSTOMER!r}"
                ),
            )
        )

        if order_ok and customer_ok:
            return ValidationResult(status="EXCELLENT", score=1.0, details=details)
        return ValidationResult(status="FAIL", score=0.0, details=details)


validator = BigHaystackValidator()
