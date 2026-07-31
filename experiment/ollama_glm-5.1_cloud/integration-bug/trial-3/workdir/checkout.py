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
    # 1. Atomically reserve stock (check + decrement in one locked operation)
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Attempt payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release the reservation
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # 3. Success: reservation confirmed by payment
    print(f"Order {order_id}: SUCCESS")
    return True