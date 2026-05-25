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
    # First, check stock under the inventory's lock and optimistically decrement
    async with inventory._lock:
        available = await inventory.check_stock(quantity)
        if not available:
            print(f"Order {order_id}: out of stock")
            return False
        # Decrement stock to reserve the item. This should always succeed due to check_stock.
        await inventory.decrement(quantity)

    # Attempt payment *outside* the inventory lock
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        # If payment fails, increment the stock back
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
