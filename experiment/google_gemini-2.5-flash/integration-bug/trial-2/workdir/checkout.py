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
    # First, try to decrement the stock atomically.
    # This prevents overselling in a concurrent environment.
    decremented = await inventory.try_decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # If stock was successfully decremented, proceed to charge.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed. Re-incrementing stock.")
        # If payment fails, put the item back in stock.
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
