"""Validator for the bug-fix challenge.

Runs the job-queue simulation in a fresh subprocess so async loops and
module state never leak between trials.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from zrb_llm_evaluator.models import TrialTrace, ValidationCheck, ValidationResult
from zrb_llm_evaluator.protocols import ValidatorProtocol

REQUIRED_FILES = ("job_queue.py", "worker.py")
RUNS = 5
CONCURRENCY_PRIMITIVES = {"Lock", "RLock", "Semaphore", "BoundedSemaphore", "Event", "Condition"}


def _instantiates_concurrency_primitive(source: str) -> bool:
    """Return True iff the source actually instantiates a concurrency primitive.

    Looks for Call nodes whose callee resolves to ``<module>.Lock()`` /
    ``Lock()`` etc. — not just the substring ``Lock`` in a comment or
    docstring. Anchors on the standard-library names rather than a free-text
    match so models can't game the check by writing ``# uses a Lock``.
    """
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


def _dequeue_has_atomic_check_and_set(source: str) -> bool:
    """Return True iff ``dequeue`` mutates the job status before any await.

    The original race was an ``await asyncio.sleep(...)`` between checking
    ``status == "pending"`` and assigning ``status = "processing"``. Reordering
    so the assignment precedes any await closes the race without a Lock —
    a valid, idiomatic fix. Detect that pattern: within an ``async def
    dequeue`` body, find an ``if`` whose test references ``status`` and
    confirm the first statement in its body is the status assignment (i.e.,
    no await sits between the check and the set).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    def _is_status_check(test: ast.AST) -> bool:
        for sub in ast.walk(test):
            if (
                isinstance(sub, ast.Subscript)
                and isinstance(sub.slice, ast.Constant)
                and sub.slice.value == "status"
            ):
                return True
        return False

    def _first_stmt_assigns_status(body: list[ast.stmt]) -> bool:
        if not body:
            return False
        first = body[0]
        if not isinstance(first, ast.Assign):
            return False
        for target in first.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "status"
            ):
                return True
        return False

    for func in ast.walk(tree):
        if not isinstance(func, ast.AsyncFunctionDef) or func.name != "dequeue":
            continue
        for node in ast.walk(func):
            if isinstance(node, ast.If) and _is_status_check(node.test):
                if _first_stmt_assigns_status(node.body):
                    return True
    return False

# Executed by a subprocess in the trial's working directory.
# Prints a single JSON line prefixed with __RESULT__ that the validator
# parses. A non-zero exit means a hard import / runtime error.
SIMULATION_SCRIPT = r"""
import asyncio, json, sys, traceback
sys.path.insert(0, ".")

try:
    from job_queue import JobQueue
    from worker import process_job
except Exception:
    print("__RESULT__" + json.dumps({"import_error": traceback.format_exc()}))
    sys.exit(0)

with open("job_queue.py") as f: queue_src = f.read()
with open("worker.py") as f: worker_src = f.read()

async def run_simulation():
    q = JobQueue(max_retries=2)
    for i in range(10):
        q.enqueue({"name": f"task_{i}", "raise_error": False})
    q.enqueue({"name": "bad_1", "raise_error": True})
    q.enqueue({"name": "bad_2", "raise_error": True})
    workers = [process_job(q, i) for i in range(5)]
    await asyncio.gather(*workers)
    jobs = q.all_jobs
    done = sum(1 for j in jobs.values() if j["status"] == "done")
    failed = sum(1 for j in jobs.values() if j["status"] == "failed")
    stuck = sum(1 for j in jobs.values() if j["status"] == "processing")
    return done, failed, stuck

runs = []
for _ in range(__RUNS__):
    try:
        runs.append(list(asyncio.run(run_simulation())))
    except Exception:
        runs.append({"error": traceback.format_exc()})

print("__RESULT__" + json.dumps({"runs": runs, "queue_src": queue_src, "worker_src": worker_src}))
""".replace("__RUNS__", str(RUNS))


def _missing_files(output_dir: Path) -> list[str]:
    return [f for f in REQUIRED_FILES if not (output_dir / f).is_file()]


def _parse_payload(stdout: str) -> dict | None:
    for line in stdout.splitlines():
        if line.startswith("__RESULT__"):
            return json.loads(line[len("__RESULT__"):])
    return None


class BugFixValidator:
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
                    message=f"Missing files: {', '.join(missing)}",
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
                    message=f"Subprocess produced no result. stderr: {proc.stderr[:500]}",
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
        for idx, run in enumerate(payload["runs"], start=1):
            if isinstance(run, dict) and "error" in run:
                details.append(
                    ValidationCheck(
                        name=f"run_{idx}",
                        passed=False,
                        message=run["error"][:400],
                    )
                )
                continue
            done, failed, stuck = run
            ok = done == 10 and failed == 2 and stuck == 0
            if ok:
                passes += 1
            details.append(
                ValidationCheck(
                    name=f"run_{idx}",
                    passed=ok,
                    message=f"done={done}, failed={failed}, stuck={stuck}",
                )
            )

        all_passed = passes == RUNS
        queue_src = payload.get("queue_src", "")
        worker_src = payload.get("worker_src", "")
        has_lock = (
            _instantiates_concurrency_primitive(queue_src)
            or _instantiates_concurrency_primitive(worker_src)
        )
        atomic_reorder = _dequeue_has_atomic_check_and_set(queue_src)
        race_closed = has_lock or atomic_reorder
        if has_lock:
            msg = "Concurrency primitive instantiated (AST-detected)"
        elif atomic_reorder:
            msg = "Race closed by reordering: status assigned before any await in dequeue"
        else:
            msg = "No Lock/Semaphore/Event instantiation and no atomic reorder in dequeue"
        details.append(
            ValidationCheck(
                name="race_condition_closed",
                passed=race_closed,
                message=msg,
            )
        )

        if not all_passed:
            return ValidationResult(
                status="FAIL",
                score=passes / RUNS,
                details=details,
            )
        if race_closed:
            return ValidationResult(status="EXCELLENT", score=1.0, details=details)
        return ValidationResult(status="PASS", score=0.85, details=details)


validator = BugFixValidator()
