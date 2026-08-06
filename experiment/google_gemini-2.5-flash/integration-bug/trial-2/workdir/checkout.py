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
    # 1. Acquire stock first to prevent overselling
    stock_acquired = await inventory.acquire_stock(order_id, quantity)
    if not stock_acquired:
        print(f"Order {order_id}: out of stock or failed to acquire")
        return False

    # 2. Process payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # If payment fails, release the acquired stock
        print(f"Order {order_id}: payment failed. Releasing stock.")
        await inventory.release_stock(order_id, quantity)
        return False

    # 3. If both stock acquired and payment successful, the order is a SUCCESS.
    # The previous `decremented` step is now part of `acquire_stock`.
    print(f"Order {order_id}: SUCCESS")
    return True
