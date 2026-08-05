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
    # Reserve stock first to prevent overselling and ghost charges
    # Since we can't change Inventory interface, we use decrement as the reservation
    if not await inventory.decrement(quantity):
        print(f"Order {order_id}: out of stock")
        return False

    try:
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            # Give back the stock since payment failed
            await inventory.increment(quantity)
            return False
    except Exception as e:
        # Ensure stock is released on unexpected errors during payment
        await inventory.increment(quantity)
        raise e

    print(f"Order {order_id}: SUCCESS")
    return True
