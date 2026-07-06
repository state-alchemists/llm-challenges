# Audit: stats.py

## What it does

Computes basic summary statistics — `average()` returns the arithmetic
mean of a list of floats; `percent()` returns one integer as a percentage
of another.

## Problem: integer floor division truncates percentages

`percent()` uses `part // whole * 100`. Because `//` is floor (integer)
division, the fractional part is discarded *before* the multiplication.
For any `part < whole` (e.g. `percent(1, 100)`), the result is `0` rather
than the expected `1`.

**Impact:** all percentage calculations where the part is smaller than
the whole silently produce zero. Analytics rollups, dashboards, and
reports that depend on this function will show incorrect (understated)
proportions. The fix is to promote the division to floating-point first:
`int(part / whole * 100)` or `int(part * 100 / whole)` (the latter
avoids intermediate float precision issues when the values are small).
