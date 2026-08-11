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
    # Decrement inventory FIRST (atomic, protected by lock)
    # This prevents overselling and ensures no charge without reserved stock
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # Payment after inventory is secured — if it fails, compensate by returning stock
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed — returning stock")
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
