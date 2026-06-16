import asyncio
from inventory import Inventory
from payments import PaymentGateway


async def checkout(
    inventory: Inventory,
    gateway: PaymentGateway,
    order_id: str,
    quantity: int,
    price: float,
) -> bool:
    if not await inventory.lock():
        print(f"Order {order_id}: inventory lock failed")
        return False

    available = await inventory.check_stock(quantity)
    if not available:
        await inventory.unlock()
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        await inventory.unlock()
        print(f"Order {order_id}: payment failed")
        return False

    decremented = await inventory.decrement(quantity)
    if not decremented:
        await inventory.unlock()
        print(f"Order {order_id}: inventory error after payment — item not delivered")
        return False

    await inventory.unlock()
    print(f"Order {order_id}: SUCCESS")
    return True
