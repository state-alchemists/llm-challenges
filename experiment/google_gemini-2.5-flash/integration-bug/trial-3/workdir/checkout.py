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
    # Try to decrement stock first (atomic check and decrement)
    decremented = await inventory.try_decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: unable to decrement stock (out of stock or race condition)")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed. Releasing reserved stock.")
        await inventory.increment(quantity)  # Release the reserved stock
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
