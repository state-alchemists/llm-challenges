# Audit: `stats.py`

## What it does

Computes basic summary statistics — arithmetic mean of a float list and
a percentage from two integers — for the analytics rollup job.

## Problems

### 1. `percent()` uses floor division before multiplication — silent truncation

`part // whole * 100` performs integer floor division first, then
multiplies by 100.  For any ratio where `part < whole`, the division
truncates to 0 before the multiplication, so every percentage that is
less than 100 % is reported as 0 %:

    percent(1, 3)   → 1 // 3 * 100 → 0 * 100 → 0
    percent(99, 100) → 99 // 100 * 100 → 0 * 100 → 0
    percent(1, 3_000_000) → 0 (expected ~0.000033 %)

This is almost certainly not the intended behaviour — the function
name, return-type annotation, and comment all suggest a genuine
percentage.

The intended expression is `(part * 100) // whole` (integer floor after
multiplication, which preserves precision for part ≥ 1) — or better,
return a `float`:

    return (part / whole) * 100   # → float, no truncation

### 2. `average()` silently returns 0.0 for an empty list

    average([])  → 0.0

This disguises a caller mistake or an upstream data-gathering failure.
An empty sample is usually an invariant violation (the rollup job had
nothing to roll up) and should raise a `ValueError`.

### Remediation

- Fix `percent()`: change `part // whole * 100` to
  `(part / whole) * 100.0` and update the return type to `float`.
  Or, if integer truncation is intentional, `(part * 100) // whole`.
- Fix `average()`: check for an empty list and raise `ValueError`
  instead of returning 0.0.
