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
    # Atomically reserve stock first — ensures we never oversell
    reserved = await inventory.decrement(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Now attempt payment — stock is already secured
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Release reserved stock so other orders can use it
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed, stock released")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
