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
    # Reserve the stock first, atomically. If it is gone, no money moves.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — return the reserved stock so another order can use it.
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Charge succeeded and the item was already reserved for this order:
    # one successful charge always corresponds to exactly one delivered item.
    print(f"Order {order_id}: SUCCESS")
    return True
