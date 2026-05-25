---
slug: checkout-toctou-race
---
# Checkout TOCTOU Race Fix

**Context:** `checkout.py` in the zrb evaluation integration-bug challenge — concurrent orders race on inventory.
**Finding:** Two bugs from the same root cause — a TOCTOU (time-of-check-time-of-use) race across async yield points (`await asyncio.sleep()`):
1. **Ghost charges**: multiple coroutines pass `check_stock` (stock ≥ quantity), then pass `charge`, then only one succeeds at `decrement` — the rest were charged but got no item.
2. **Overselling**: `decrement` itself has a yield point (`await asyncio.sleep(0.02)`) between the guard check and the subtraction, so all coroutines that enter `decrement` will subtract.

**Fix:** Added `asyncio.Lock()` to `Inventory` and wrapped the critical section (check_stock → charge → decrement) in `async with inventory.lock:` inside `checkout()`.
**Source:** `checkout.py:13`, `inventory.py:7`
