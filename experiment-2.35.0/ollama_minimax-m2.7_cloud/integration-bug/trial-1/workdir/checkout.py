import asyncio
from inventory import Inventory
from payments import PaymentGateway


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # Decrement inventory FIRST — atomically checks stock and reserves it.
    # This eliminates the TOCTOU race where check_stock passed but another
    # coroutine depleted stock before decrement ran.
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # Inventory is now reserved. If payment fails, restore it.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed — restoring inventory")
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
