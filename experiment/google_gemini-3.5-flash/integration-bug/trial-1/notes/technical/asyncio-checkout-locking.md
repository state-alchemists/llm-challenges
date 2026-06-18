# Asyncio Checkout Locking

To prevent race conditions where multiple concurrent checkouts check stock, charge payments, and then decrement stock (which leads to ghost charges and overselling), we use a module-level `asyncio.Lock` to serialize the entire checkout flow in `checkout.py`.

## Details
1. **Problem**: Because `inventory.check_stock`, `gateway.charge`, and `inventory.decrement` are asynchronous, concurrent orders execute them concurrently. Since payment takes 0.03 seconds, multiple orders check stock and proceed to payment before stock is actually decremented. This results in:
   - Multiple orders paying for the same limited item.
   - Later orders failing to decrement stock (ghost charges).
2. **Solution**: Serializing the entire checkout operation ensures that stock checks and decrements are handled atomically with respect to payment processing, ensuring:
   - Inventory never goes negative.
   - No order is charged without inventory being secured.
   - Total charges always match the successfully completed orders.

## Backlinks
- [index.md](../index.md) — main journal index
