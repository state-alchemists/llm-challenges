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
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    charged = False
    try:
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            return False

        print(f"Order {order_id}: SUCCESS")
        return True
    finally:
        if not charged:
            # Restore stock if payment failed, raised an exception, or was cancelled.
            # We shield the increment so it runs to completion even if this task is cancelled.
            await asyncio.shield(inventory.increment(quantity))
