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
    # First, try to decrement inventory. This acts as an atomic check and reservation.
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock or inventory error")
        return False

    # Now attempt to charge. If this fails, we must increment stock back.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed. Restoring inventory.")
        await inventory.increment(quantity)  # Restore stock
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
