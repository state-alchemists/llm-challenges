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
    # Decrement stock first to "reserve" it
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    try:
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            # Payment failed, so return stock back to inventory
            await inventory.increment(quantity)
            print(f"Order {order_id}: payment failed")
            return False
    except BaseException as e:
        # If an unexpected error or cancellation happens, restore stock
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment error/cancelled — {e}")
        raise e

    print(f"Order {order_id}: SUCCESS")
    return True
