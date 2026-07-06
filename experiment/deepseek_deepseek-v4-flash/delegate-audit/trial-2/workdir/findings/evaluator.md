# Audit: evaluator.py

## What it does

Evaluates user-supplied arithmetic rule strings (e.g. `"base * 1.2 +
surcharge"`) against a context dict for the pricing engine. Rules are
provided by account managers through the admin console.

## Problem: arbitrary code execution via `eval()`

`apply_rule()` passes user-supplied input directly to Python's `eval()`.
Stripping `__builtins__` is a known-insufficient defence — it is
trivially bypassed via Python's class introspection chain (e.g.
`().__class__.__bases__[0].__subclasses__()` to recover `os.system` or
`subprocess.Popen`).

**Impact:** an account manager (or anyone who compromises that account)
can execute arbitrary shell commands on the pricing-engine process
hosting the evaluator. This is a full RCE vulnerability. `eval()` on
untrusted input must never reach production — use a restricted expression
parser (e.g. a simple AST walker that whitelists operators and names) or
a sandboxed arithmetic evaluator instead.
