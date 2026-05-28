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
    # Atomically check stock and decrement
    decremented = await inventory._atomic_decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock or inventory error")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed. Attempting inventory rollback.")
        # If payment fails, increment stock back to prevent ghost charges
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
