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
    # 1. Reserve the stock first
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Since stock is successfully reserved, attempt payment charge
    try:
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            # Rollback inventory reservation on payment failure
            await inventory.increment(quantity)
            return False
    except Exception as e:
        # Rollback inventory reservation on unexpected exception during payment
        await inventory.increment(quantity)
        raise e

    print(f"Order {order_id}: SUCCESS")
    return True
