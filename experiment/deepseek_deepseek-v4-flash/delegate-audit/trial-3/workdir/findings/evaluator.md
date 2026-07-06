# Audit: evaluator.py

**What it does:** Evaluates user-supplied arithmetic expression strings
(e.g. `"base * 1.2 + surcharge"`) against a context dictionary to
compute a price for the pricing engine. Account managers supply these
rules through the admin console.

**Problem — remote code execution via `eval()`:**

The `apply_rule` function passes a user-supplied string directly to
Python's `eval()`. While `{"__builtins__": {}}` removes the `builtins`
name from the evaluation namespace, this is **not** a security boundary.

Python's `eval()` with an empty builtins namespace can still be
subverted through the object-model chain:

```python
eval("(lambda: 0).__code__.__class__.__subclasses__()", ...)
```

This reliably reaches `os.system` or `subprocess.Popen` through the
subclasses of `object`, giving the attacker arbitrary shell execution
on the server.

Since the input comes from account managers via the admin console — a
surface that is likely accessible over the network and may be reachable
by non-admin users — this is a critical RCE vulnerability.

**Fix:** Replace `eval()` with a safe expression parser (e.g. `ast.literal_eval`,
a simple shunting-yard evaluator, or a dedicated expression-language
library like `simpleeval`).
