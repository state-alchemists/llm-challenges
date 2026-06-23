import asyncio
from inventory import Inventory
from payments import PaymentGateway

# Global registries to manage concurrent duplicate order checkouts safely
_active_orders = set()
_completed_orders = {}  # order_id -> bool (success status)

async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # 1. Prevent duplicate checkout attempts for the same order_id concurrently or previously
    if order_id in _completed_orders:
        return _completed_orders[order_id]
        
    if order_id in _active_orders:
        # Wait for the active checkout for this order_id to finish
        while order_id in _active_orders:
            await asyncio.sleep(0.01)
        return _completed_orders.get(order_id, False)

    _active_orders.add(order_id)
    try:
        # Check payment gateway charges list directly to avoid duplicate charge if already charged
        if any(charge["order_id"] == order_id for charge in gateway.charges):
            _completed_orders[order_id] = True
            return True

        # 2. Try to reserve stock. Since other checkouts may fail payment and release stock,
        # we retry stock acquisition periodically.
        decremented = False
        for _ in range(15):
            decremented = await inventory.decrement(quantity)
            if decremented:
                break
            await asyncio.sleep(0.02)

        if not decremented:
            print(f"Order {order_id}: out of stock")
            _completed_orders[order_id] = False
            return False

        # 3. Process payment once stock reservation is secured
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            # Release the reserved stock immediately upon payment failure
            await inventory.increment(quantity)
            _completed_orders[order_id] = False
            return False

        print(f"Order {order_id}: SUCCESS")
        _completed_orders[order_id] = True
        return True
    finally:
        _active_orders.discard(order_id)
