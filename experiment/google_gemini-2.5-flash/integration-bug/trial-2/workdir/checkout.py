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
    # 1. Attempt to decrement inventory first (atomic operation)
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock or inventory error")
        return False

    # 2. If inventory decremented, attempt to charge
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed. Refunding inventory.")
        # If payment fails, increment inventory back (rollback)
        await inventory.increment(quantity)
        return False

    # 3. Both inventory decremented and payment successful
    print(f"Order {order_id}: SUCCESS")
    return True
