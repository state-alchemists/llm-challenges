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
    # Reserve inventory FIRST — this atomically decrements stock
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Charge the customer
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — restore the reserved inventory
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Payment succeeded — item is already decremented (reserved), delivery is implicit
    print(f"Order {order_id}: SUCCESS")
    return True
