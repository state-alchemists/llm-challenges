"""Validator for the checkout integration-bug challenge.

Runs the concurrent checkout simulation in a subprocess to keep the
asyncio loop / module state independent across trials.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from zrb_llm_evaluator.models import TrialTrace, ValidationCheck, ValidationResult
from zrb_llm_evaluator.protocols import ValidatorProtocol

REQUIRED_FILES = ("inventory.py", "payments.py", "checkout.py")
TRIALS = 6
CONCURRENCY_PRIMITIVES = {"Lock", "RLock", "Semaphore", "BoundedSemaphore", "Event", "Condition"}


def _instantiates_concurrency_primitive(source: str) -> bool:
    """Return True iff the source actually instantiates a concurrency primitive."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in CONCURRENCY_PRIMITIVES:
            return True
        if isinstance(func, ast.Name) and func.id in CONCURRENCY_PRIMITIVES:
            return True
    return False

SIMULATION_SCRIPT = r"""
import asyncio, json, random, sys, traceback
sys.path.insert(0, ".")

try:
    from inventory import Inventory
    from payments import PaymentGateway
    from checkout import checkout
except Exception:
    print("__RESULT__" + json.dumps({"import_error": traceback.format_exc()}))
    sys.exit(0)

with open("inventory.py") as f: inv_src = f.read()
with open("checkout.py") as f: checkout_src = f.read()

async def run_one(seed):
    random.seed(seed)
    inventory = Inventory(5)
    gateway = PaymentGateway(failure_rate=0.25)
    orders = [checkout(f"order_{i}", 1, 100.0, inventory, gateway) for i in range(12)]
    results = await asyncio.gather(*orders)
    successful = sum(results)
    charge_ids = [c["order_id"] for c in gateway.charges]
    duplicates = len(charge_ids) - len(set(charge_ids))
    return [inventory.stock, gateway.total_charged, successful, duplicates, successful * 100.0]

results = []
for t in range(__TRIALS__):
    try:
        results.append(asyncio.run(run_one(t * 7)))
    except Exception:
        results.append({"error": traceback.format_exc()})

print("__RESULT__" + json.dumps({"trials": results, "inv_src": inv_src, "checkout_src": checkout_src}))
""".replace("__TRIALS__", str(TRIALS))


def _missing_files(output_dir: Path) -> list[str]:
    return [f for f in REQUIRED_FILES if not (output_dir / f).is_file()]


def _parse_payload(stdout: str) -> dict | None:
    for line in stdout.splitlines():
        if line.startswith("__RESULT__"):
            return json.loads(line[len("__RESULT__"):])
    return None


class IntegrationBugValidator:
    def validate(
        self,
        output_dir: Path,
        log_content: str,
        trace: TrialTrace | None = None,
    ) -> ValidationResult:
        details: list[ValidationCheck] = []
        missing = _missing_files(output_dir)
        if missing:
            details.append(
                ValidationCheck(
                    name="required_files",
                    passed=False,
                    message=f"Missing: {', '.join(missing)}",
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)

        proc = subprocess.run(
            [sys.executable, "-c", SIMULATION_SCRIPT],
            cwd=str(output_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        payload = _parse_payload(proc.stdout)
        if payload is None:
            details.append(
                ValidationCheck(
                    name="simulation_subprocess",
                    passed=False,
                    message=f"No result. stderr: {proc.stderr[:500]}",
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)

        if "import_error" in payload:
            details.append(
                ValidationCheck(
                    name="import",
                    passed=False,
                    message=payload["import_error"][:500],
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)

        passes = 0
        for idx, trial in enumerate(payload["trials"], start=1):
            if isinstance(trial, dict) and "error" in trial:
                details.append(
                    ValidationCheck(
                        name=f"trial_{idx}",
                        passed=False,
                        message=trial["error"][:400],
                    )
                )
                continue
            stock, charged, successful, dupes, expected = trial
            errors = []
            if stock < 0:
                errors.append(f"negative stock ({stock})")
            if abs(charged - expected) > 0.01:
                errors.append(f"charge mismatch (charged={charged:.2f}, expected={expected:.2f})")
            if dupes > 0:
                errors.append(f"{dupes} duplicate charge(s)")
            ok = not errors
            if ok:
                passes += 1
                msg = f"stock={stock}, successful={successful}, charged=${charged:.2f}"
            else:
                msg = ", ".join(errors)
            details.append(
                ValidationCheck(name=f"trial_{idx}", passed=ok, message=msg)
            )

        all_passed = passes == TRIALS
        inv_src = payload.get("inv_src", "")
        checkout_src = payload.get("checkout_src", "")
        has_lock = (
            _instantiates_concurrency_primitive(inv_src)
            or _instantiates_concurrency_primitive(checkout_src)
        )
        details.append(
            ValidationCheck(
                name="locking_mechanism",
                passed=has_lock,
                message="Concurrency primitive instantiated (AST-detected)"
                if has_lock
                else "No Lock/Semaphore/Event instantiation found in source",
            )
        )

        if not all_passed:
            return ValidationResult(
                status="FAIL",
                score=passes / TRIALS,
                details=details,
            )
        if has_lock:
            return ValidationResult(status="EXCELLENT", score=1.0, details=details)
        return ValidationResult(status="PASS", score=0.85, details=details)


validator = IntegrationBugValidator()
