import asyncio
from inventory import Inventory
from payments import PaymentGateway

# Fine-grained per-order locks with reference counting to prevent leaks
_order_locks = {}
_order_ref_counts = {}
_order_locks_lock = asyncio.Lock()


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # 1. Acquire fine-grained lock for this specific order_id
    async with _order_locks_lock:
        if order_id not in _order_locks:
            _order_locks[order_id] = asyncio.Lock()
            _order_ref_counts[order_id] = 0
        _order_ref_counts[order_id] += 1
        lock = _order_locks[order_id]

    try:
        async with lock:
            # 2. Idempotency check: has this order already been charged?
            for charge in gateway.charges:
                if charge["order_id"] == order_id:
                    return True

            decremented = False
            try:
                # 3. Reserve stock (atomic decrement)
                decremented = await inventory.decrement(quantity)
                if not decremented:
                    print(f"Order {order_id}: out of stock")
                    return False

                # 4. Attempt to charge customer
                charged = await gateway.charge(order_id, quantity * price)
                if not charged:
                    print(f"Order {order_id}: payment failed")
                    return False

                print(f"Order {order_id}: SUCCESS")
                return True

            except Exception as e:
                print(f"Order {order_id}: unexpected error {e}")
                raise

            finally:
                # 5. Clean up / rollback stock if decremented but payment failed
                was_charged = any(c["order_id"] == order_id for c in gateway.charges)
                if decremented and not was_charged:
                    await asyncio.shield(inventory.increment(quantity))

    finally:
        # 6. Release lock and clean up order_locks references
        async with _order_locks_lock:
            _order_ref_counts[order_id] -= 1
            if _order_ref_counts[order_id] == 0:
                del _order_locks[order_id]
                del _order_ref_counts[order_id]
