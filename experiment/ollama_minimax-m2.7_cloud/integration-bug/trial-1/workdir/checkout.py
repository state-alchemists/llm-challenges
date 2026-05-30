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
    # 1. Atomically reserve inventory — prevents overselling
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Capture payment
    amount = quantity * price
    charged = await gateway.charge(order_id, amount)
    if not charged:
        # Payment failed — release the reserved inventory
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
