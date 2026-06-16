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
    # First, try to decrement inventory. This is now atomic.
    # If this fails, it means stock is truly unavailable or a race condition was lost.
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock or inventory error")
        return False

    # Attempt payment.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed. Attempting to restock.")
        # If payment fails, we must undo the inventory decrement.
        await inventory.increment(quantity)
        return False

    # If both inventory decrement and payment succeed, the order is successful.
    print(f"Order {order_id}: SUCCESS")
    return True
