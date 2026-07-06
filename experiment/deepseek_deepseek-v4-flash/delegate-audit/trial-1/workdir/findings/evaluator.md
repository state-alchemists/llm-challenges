# Audit: `evaluator.py`

## What it does

Evaluates user-supplied arithmetic expressions (pricing rules) against a
context dictionary, intended for use in a pricing-engine admin console.

## Problem — Arbitrary code execution via `eval()`

`apply_rule()` calls Python's built-in `eval()` on a string provided by
the caller.  While `{"__builtins__": {}}` strips the builtins namespace,
this is a well-studied insufficient defense:

- An attacker can reach builtins through other dunder chains
  (e.g. via `().__class__.__bases__[0].__subclasses__()`).
- The docstring confirms the input originates from account managers
  through the admin console — i.e. a user-facing surface.

### Impact

- Any user who can submit a pricing rule (even via an authenticated
  admin console) can execute arbitrary Python bytecode on the server.
- Full server compromise: process memory access, environment-variable
  exfiltration, lateral movement to the database.

### Remediation

- Replace `eval()` with a safe expression parser.  `ast.literal_eval`
  won't work here (it doesn't support operators like `+`, `*`).
  Use a library built for this purpose:
    - Python's built-in `ast.parse` + a whitelist-based AST visitor
    - The `simpleeval` PyPI package
    - A restricted DSL compiled via `numexpr` for numeric expressions
- Add input validation: reject anything that doesn't match a strict
  pattern like `[a-zA-Z0-9_+\-*/.() ]+`.
- Never pass user-supplied strings to `eval()` — the sandbox is
  illusory.
