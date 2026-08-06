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
    # Decrement inventory FIRST — this is the only atomic point.
    # If decrement fails, order cannot be fulfilled; do not charge.
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # Inventory is now reserved. If charge fails, restore it.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        await inventory.restore(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
