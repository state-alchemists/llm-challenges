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
    # Attempt to reserve stock first to prevent overselling/ghost charges
    # We can't change the public interface, but we can add methods to Inventory.
    # For now, let's use the available methods.
    
    # To prevent overselling, we must decrement BEFORE charging or use a reservation system.
    # If we decrement first, we must increment (refund stock) if payment fails.
    
    # 1. Try to decrement stock immediately (Atomic check-and-decrement)
    if not await inventory.decrement(quantity):
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Try to charge the user
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        # Payment failed, return stock to inventory
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
