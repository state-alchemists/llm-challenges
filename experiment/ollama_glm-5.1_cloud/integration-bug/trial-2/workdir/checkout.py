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
    # Reserve stock atomically — prevents overselling by ensuring
    # check-and-decrement happen under a single lock.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Charge only after reservation succeeds.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release the reserved stock back.
        await inventory.release(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Reservation + charge both succeeded — item is delivered.
    print(f"Order {order_id}: SUCCESS")
    return True