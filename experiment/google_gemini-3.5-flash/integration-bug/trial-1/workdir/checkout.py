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
    # Reserve stock first
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # Stock is reserved, charge payment gateway
    try:
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            # Revert stock reservation if payment fails
            await inventory.increment(quantity)
            print(f"Order {order_id}: payment failed")
            return False
    except BaseException as e:
        # Revert stock reservation if payment raises exception or is cancelled
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment error/cancelled — {e}")
        raise

    print(f"Order {order_id}: SUCCESS")
    return True
