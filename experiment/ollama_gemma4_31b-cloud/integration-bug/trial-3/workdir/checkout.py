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
    # 1. Reserve inventory first to prevent overselling and ghost charges
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Attempt payment only after inventory is secured
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        # Compensating transaction: return the reserved item to inventory
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
