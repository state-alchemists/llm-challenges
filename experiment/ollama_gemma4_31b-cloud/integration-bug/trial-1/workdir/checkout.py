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
    # Atomic check and decrement to prevent overselling
    # Note: we can't change Inventory interface, but we can add a method or just use decrement
    # In the current implementation, decrement already checks stock.
    # To avoid "Ghost Charges", we should either decrement first or refund on failure.
    
    # Strategy: Try to decrement first (reserve). If it fails, we are out of stock.
    # If it succeeds, we charge. If charge fails, we increment back.
    
    if not await inventory.decrement(quantity):
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
