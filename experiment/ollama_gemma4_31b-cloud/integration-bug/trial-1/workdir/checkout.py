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
    # Atomically attempt to decrement stock first to prevent overselling
    # and Time-of-Check to Time-of-Use (TOC/TOU) race conditions.
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    try:
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            # Give stock back if payment fails
            await inventory.increment(quantity)
            return False

        print(f"Order {order_id}: SUCCESS")
        return True
    except Exception as e:
        # Ensure stock is restored if any unexpected error occurs during payment
        await inventory.increment(quantity)
        print(f"Order {order_id}: unexpected error {e}")
        return False
