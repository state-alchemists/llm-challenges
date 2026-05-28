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
    # Reserve stock first to ensure we have the items before charging
    # We can use decrement as a reservation since we now have a lock
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    try:
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            # Roll back stock reservation
            await inventory.increment(quantity)
            return False
    except Exception as e:
        # Ensure stock is returned if payment gateway crashes
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment system error: {e}")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
