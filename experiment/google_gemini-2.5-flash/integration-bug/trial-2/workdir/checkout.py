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
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Attempt to charge the customer
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed. Releasing reserved stock.")
        await inventory.release(quantity)
        return False

    # 3. If payment successful, no need to decrement again as reserve already did.
    # The item is considered delivered at this point.

    print(f"Order {order_id}: SUCCESS")
    return True
