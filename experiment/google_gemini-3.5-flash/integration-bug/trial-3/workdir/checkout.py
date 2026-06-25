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
    # Reserve stock first to prevent overselling and race conditions
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    try:
        charged = await gateway.charge(order_id, quantity * price)
    except Exception as e:
        # If charging raises an exception, we must restore the reserved inventory
        await inventory.increment(quantity)
        raise e

    if not charged:
        print(f"Order {order_id}: payment failed")
        # Payment failed, so restore the reserved inventory
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
