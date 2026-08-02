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
    # 1. Atomically reserve stock first — no TOCTOU gap
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Charge the customer
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — give the stock back
        await inventory.restore(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Stock is reserved and paid for — order complete
    print(f"Order {order_id}: SUCCESS")
    return True
