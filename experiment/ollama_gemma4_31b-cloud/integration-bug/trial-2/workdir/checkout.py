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
    # Reserve stock first to prevent overselling
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    try:
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            # Return stock if payment fails
            await inventory.increment(quantity)
            return False
    except Exception as e:
        # Ensure stock is returned if an unexpected error occurs during payment
        await inventory.increment(quantity)
        print(f"Order {order_id}: unexpected error during payment: {e}")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
