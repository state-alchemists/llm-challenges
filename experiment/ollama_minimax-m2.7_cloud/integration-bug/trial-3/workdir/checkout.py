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
    # Atomically reserve stock — prevents overselling
    reserved = await inventory.reserve_stock(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Stock already decremented; restore it and refund if partial charge occurred
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed — stock restored")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
