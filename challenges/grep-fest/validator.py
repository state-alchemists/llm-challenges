"""Validator for the grep-fest challenge.

AST-scans every .py file under the agent's workdir for residual
``legacy_auth`` call sites. The definition in ``app/auth.py`` is exempt
(it must remain). Also confirms the package still imports cleanly.

Scoring buckets:
- 1.0 EXCELLENT: zero residual call sites AND the package imports
  AND ``scope="write"`` is used in modules whose names indicate writes
  (``*create*``, ``*update*``, ``*delete*``, ``*sync*``, ``*importer*``,
  ``*cleanup*``, ``*billing*``, ``*notifier*``, ``*mailer*``,
  ``*tokens_repo*``, ``*audit_repo*``).
- 0.8 PASS: zero residual call sites AND the package imports, but the
  agent used the same scope everywhere (mechanical replace).
- 0.0–0.6 FAIL: residual call sites or import broken.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from zrb_llm_evaluator.models import TrialTrace, ValidationCheck, ValidationResult
from zrb_llm_evaluator.protocols import ValidatorProtocol

# Files where ``legacy_auth`` may still appear (the canonical definition).
EXEMPT_PATHS = {"app/auth.py"}
# Module-name substrings that signal a write call site — agent should
# pass scope="write" in these modules.
WRITE_HINT_SUBSTRINGS = (
    "create",
    "update",
    "delete",
    "sync",
    "importer",
    "cleanup",
    "billing",
    "notifier",
    "mailer",
    "tokens_repo",
    "audit_repo",
    "uploads",
)


def _residual_legacy_calls(root: Path) -> list[tuple[str, int]]:
    """Return [(relpath, lineno), ...] for every Call to legacy_auth(...)."""
    hits: list[tuple[str, int]] = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root).as_posix()
        if rel in EXEMPT_PATHS:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "legacy_auth":
                hits.append((rel, node.lineno))
            elif isinstance(func, ast.Attribute) and func.attr == "legacy_auth":
                hits.append((rel, node.lineno))
    return hits


def _new_auth_scope_args(root: Path) -> list[tuple[str, int, str]]:
    """Return [(relpath, lineno, scope_value), ...] for every new_auth(...) call.

    ``scope_value`` is the string literal passed as ``scope=``, or
    ``"<missing>"`` if scope wasn't passed, or ``"<dynamic>"`` if it's not a
    plain string literal.
    """
    out: list[tuple[str, int, str]] = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root).as_posix()
        if rel in EXEMPT_PATHS:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name != "new_auth":
                continue
            scope_val = "<missing>"
            for kw in node.keywords:
                if kw.arg == "scope":
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        scope_val = kw.value.value
                    else:
                        scope_val = "<dynamic>"
            if len(node.args) >= 2 and scope_val == "<missing>":
                if isinstance(node.args[1], ast.Constant) and isinstance(
                    node.args[1].value, str
                ):
                    scope_val = node.args[1].value
                else:
                    scope_val = "<dynamic>"
            out.append((rel, node.lineno, scope_val))
    return out


class GrepFestValidator:
    def validate(
        self,
        output_dir: Path,
        log_content: str,
        trace: TrialTrace | None = None,
    ) -> ValidationResult:
        details: list[ValidationCheck] = []

        if not (output_dir / "app" / "auth.py").is_file():
            details.append(
                ValidationCheck(
                    name="auth_module_present",
                    passed=False,
                    message="app/auth.py is missing — agent removed the definition",
                )
            )
            return ValidationResult(status="FAIL", score=0.0, details=details)

        residual = _residual_legacy_calls(output_dir)
        zero_residual = len(residual) == 0
        details.append(
            ValidationCheck(
                name="no_residual_legacy_calls",
                passed=zero_residual,
                message=(
                    f"{len(residual)} residual legacy_auth call(s): "
                    + ", ".join(f"{r}:{ln}" for r, ln in residual[:5])
                )
                if not zero_residual
                else "Zero residual legacy_auth call sites",
            )
        )

        # Importability — run in a subprocess to keep our process untouched.
        proc = subprocess.run(
            [sys.executable, "-c", "import sys; sys.path.insert(0, '.'); import app"],
            cwd=str(output_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        imports_ok = proc.returncode == 0
        details.append(
            ValidationCheck(
                name="package_imports",
                passed=imports_ok,
                message=("import app exits 0" if imports_ok
                        else f"import failed: {proc.stderr[:400]}"),
            )
        )

        new_calls = _new_auth_scope_args(output_dir)
        write_hint_modules = [
            rel for rel, _, _ in new_calls
            if any(hint in rel for hint in WRITE_HINT_SUBSTRINGS)
        ]
        scopes_in_write_modules = [
            scope for rel, _, scope in new_calls
            if any(hint in rel for hint in WRITE_HINT_SUBSTRINGS)
        ]
        used_write_scope = any(s == "write" for s in scopes_in_write_modules)
        write_modules_present = len(write_hint_modules) > 0
        details.append(
            ValidationCheck(
                name="scope_write_used_for_write_modules",
                passed=used_write_scope if write_modules_present else True,
                message=(
                    f"{sum(1 for s in scopes_in_write_modules if s == 'write')}"
                    f"/{len(scopes_in_write_modules)} new_auth calls in write-like "
                    f"modules use scope=\"write\""
                    if write_modules_present
                    else "no write-like modules detected"
                ),
            )
        )

        if not zero_residual or not imports_ok:
            return ValidationResult(status="FAIL", score=0.3, details=details)

        if used_write_scope:
            return ValidationResult(status="EXCELLENT", score=1.0, details=details)
        return ValidationResult(status="PASS", score=0.8, details=details)


validator = GrepFestValidator()
