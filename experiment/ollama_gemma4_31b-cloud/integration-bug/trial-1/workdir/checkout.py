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
    # Try to reserve stock first to avoid charging for unavailable items
    # Use decrement immediately as the "reservation"
    success = await inventory.decrement(quantity)
    if not success:
        print(f"Order {order_id}: out of stock")
        return False

    try:
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            # Release stock if payment fails
            await inventory.increment(quantity)
            return False
    except Exception as e:
        # Handle unexpected payment errors by releasing stock
        await inventory.increment(quantity)
        print(f"Order {order_id}: unexpected error during payment: {e}")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
