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
    # 1. Reserve stock first to prevent overselling
    # This ensures we have the item before we take the money.
    if not await inventory.decrement(quantity):
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Attempt payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        # 3. Compensate: return stock if payment failed
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
