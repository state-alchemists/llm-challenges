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
    available = await inventory.check_stock(quantity)
    if not available:
        print(f"Order {order_id}: out of stock")
        return False

    # Reserve stock first
    decremented = await inventory.decrement(quantity)
    if not decremented:  # No need to charge if inventory is unavailable
        print(f"Order {order_id}: inventory issue, cannot process order")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed; returning stock")
        await inventory.increment(quantity)  # Rollback inventory on charge failure
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
