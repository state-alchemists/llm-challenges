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
    # Atomically reserve stock — no TOCTOU gap between check and decrement
    if not await inventory.reserve(quantity):
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release the reservation so another order can use it
        await inventory.cancel_reservation(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Stock was reserved and payment succeeded — item delivered
    print(f"Order {order_id}: SUCCESS")
    return True
