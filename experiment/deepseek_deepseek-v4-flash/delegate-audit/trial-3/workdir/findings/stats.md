# Audit: stats.py

**What it does:** Computes basic summary statistics — `average` (the
arithmetic mean of a float list) and `percent` (one integer as a
percentage of another) — for the analytics rollup job.

**Problem — integer-division ordering bug in `percent()`:**

```python
def percent(part: int, whole: int) -> int:
    return part // whole * 100
```

Integer division truncates **before** the multiplication, so for any
`part < whole` the intermediate result is 0, and the final result is 0.

Examples:
- `percent(1, 3)`  → `0`   (should be `33`)
- `percent(50, 100)` → `0` (should be `50`)
- `percent(99, 100)` → `0` (should be `99`)
- `percent(100, 100)` → `100` (correct by coincidence)

The result is always 0 until `part >= whole`, making the function
effectively broken for its intended "X out of Y" use case.

**Fix:** Multiply before dividing: `return part * 100 // whole`.
