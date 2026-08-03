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
    # 1. Try to decrement (reserve) the stock first.
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Charge the customer.
    try:
        charged = await gateway.charge(order_id, quantity * price)
    except Exception:
        # If charge raises an error, rollback inventory reservation
        await inventory.increment(quantity)
        raise

    if not charged:
        # 3. Payment failed, rollback inventory reservation
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
