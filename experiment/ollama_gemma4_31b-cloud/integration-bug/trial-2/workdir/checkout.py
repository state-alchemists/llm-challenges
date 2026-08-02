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
    # Step 1: Reserve stock before payment.
    # This prevents overselling and avoids charging users when stock isn't actually available.
    if not await inventory.decrement(quantity):
        print(f"Order {order_id}: out of stock")
        return False

    try:
        # Step 2: Charge the user.
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            # Release stock if payment fails.
            await inventory.increment(quantity)
            return False
    except Exception as e:
        print(f"Order {order_id}: Unexpected error during payment: {e}")
        await inventory.increment(quantity)
        raise

    print(f"Order {order_id}: SUCCESS")
    return True
