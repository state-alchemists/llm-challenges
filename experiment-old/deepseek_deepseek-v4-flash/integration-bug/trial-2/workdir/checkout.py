from inventory import Inventory
from payments import PaymentGateway


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # Phase 1: Reserve inventory (atomic check + decrement under lock)
    async with inventory.lock:
        available = await inventory.check_stock(quantity)
        if not available:
            print(f"Order {order_id}: out of stock")
            return False
        if not await inventory.decrement(quantity):
            print(f"Order {order_id}: out of stock (race)")
            return False

    # Phase 2: Charge — outside the lock (I/O can proceed in parallel)
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Compensate: release reserved stock
        async with inventory.lock:
            await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
