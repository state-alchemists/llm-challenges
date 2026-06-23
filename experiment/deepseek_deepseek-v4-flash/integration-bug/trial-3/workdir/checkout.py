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
    # Phase 1: Atomically reserve stock (check + decrement under lock)
    reserved = await inventory.try_reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Phase 2: Process payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release reserved stock for another customer
        await inventory.release(quantity)
        print(f"Order {order_id}: payment failed — stock released")
        return False

    # Stock is already decremented from try_reserve, and payment succeeded
    print(f"Order {order_id}: SUCCESS")
    return True
