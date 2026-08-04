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
    # 1. Atomically try to decrement stock
    decremented = await inventory.try_decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock or inventory error")
        return False

    # 2. Attempt payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed. Releasing reserved stock.")
        # Compensation: if payment fails, increment the inventory back
        await inventory.increment(quantity)
        return False

    # 3. If both stock decrement and payment successful, order is complete
    print(f"Order {order_id}: SUCCESS")
    return True
