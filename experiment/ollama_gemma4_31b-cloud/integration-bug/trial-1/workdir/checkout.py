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
    # 1. Reserve stock first to prevent overselling
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Charge the customer
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        # Release the reservation if payment fails
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
