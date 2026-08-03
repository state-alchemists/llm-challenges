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
    # Reserve (and deliver) inventory atomically BEFORE charging. This is the
    # commit point: reservation is check+decrement under one lock, so we can
    # never oversell, and a charge only ever follows a successful reservation
    # — no item, no charge.
    reserved = await inventory.try_reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed: give the reserved stock back.
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
