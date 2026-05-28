---
slug: concurrent-checkout-race-fix
---
# Concurrent Checkout Race Fix

**Context:** E-commerce checkout with async concurrency — `asyncio.gather` fans out 12+ `checkout()` coroutines against shared `Inventory` and `PaymentGateway` objects.

**Finding:** The original checkout flow (`check_stock` → `charge` → `decrement`) has two race conditions:

1. **TOCTOU between `check_stock` and `decrement`** — all concurrent orders see stock as available, proceed to `charge`, but only some win the `decrement` race. The losers are charged but receive no item (ghost charges).

2. **Read-modify-write in `decrement`** — the `if self._stock >= qty` check and `self._stock -= qty` assignment are separate bytecodes. Under the GIL, a context switch between them lets two coroutines decrement from the same base value, overselling inventory.

**Fix:** Reserve-before-charge pattern. Added `try_reserve()` (atomic check+decrement under `asyncio.Lock`) and `release()` (return stock) to `Inventory`. Checkout becomes `try_reserve` → `charge` → (on failure) `release`. Stock is decremented atomically before payment, so no concurrent checkout can reserve the last unit twice. If payment fails, the reservation is rolled back atomically.

**Source:** `inventory.py:38-47`, `checkout.py:12-26`
