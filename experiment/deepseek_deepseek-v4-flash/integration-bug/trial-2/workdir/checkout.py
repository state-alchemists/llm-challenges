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
    # Reserve stock first — this is the point of no return for inventory.
    # decrement() atomically checks and debits stock (no await between
    # its guard and its -=), so concurrent orders don't oversell here.
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # Now attempt payment against the reserved stock.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release the reservation so another order can use it.
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed, stock released")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
