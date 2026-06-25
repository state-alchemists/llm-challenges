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
    if not await inventory.atomic_decrement(quantity):
        print(f"Order {order_id}: out of stock or inventory error")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed, rolling back inventory")
        await inventory.increment(quantity)  # Rollback inventory
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
