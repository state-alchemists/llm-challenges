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
    # Use a combined check-and-decrement to avoid race conditions
    # although we added a lock in Inventory, checking then charging then decrementing
    # still leaves a window where stock can be taken by others.
    # The best way to ensure "no overselling" is to reserve stock first.
    
    # 1. Attempt to reserve stock (decrement)
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Attempt to charge
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Release stock if payment fails
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
