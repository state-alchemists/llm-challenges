import asyncio
from inventory import Inventory
from payments import PaymentGateway


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
    # 1. Try to reserve stock atomically
    reserved = await inventory.try_reserve_stock(order_id, quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock or reservation failed")
        return False

    # 2. Attempt to charge the customer
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed. Releasing reserved stock.")
        await inventory.release_reserved_stock(quantity)
        return False

    # If both reservation and charge succeeded, the order is successful.
    print(f"Order {order_id}: SUCCESS")
    return True
