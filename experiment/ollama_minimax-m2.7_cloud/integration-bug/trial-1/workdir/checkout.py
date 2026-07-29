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
    # Decrement inventory FIRST (atomic check-and-decrement)
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # Charge AFTER successful inventory reservation
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Refund: restore inventory since we couldn't collect payment
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed — inventory restored")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
