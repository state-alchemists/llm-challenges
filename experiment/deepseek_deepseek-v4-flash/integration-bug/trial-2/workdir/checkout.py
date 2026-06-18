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
    # Reserve inventory first — this is the single authoritative stock check.
    # No separate check_stock call means no TOCTOU race with other coroutines.
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # Only charge after inventory is secured. If payment fails, release stock.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed — stock released")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
