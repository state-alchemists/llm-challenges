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
    # 1. Atomic Stock Reservation
    # We decrement first to "reserve" the item.
    # This prevents overselling because the decrement is the source of truth.
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        # Refund the stock reservation since payment failed
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
