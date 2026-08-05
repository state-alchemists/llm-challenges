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
    # Reserve stock first. reserve() checks availability and decrements in one
    # synchronous block, so concurrent checkouts can never oversell.
    if not await inventory.reserve(quantity):
        print(f"Order {order_id}: out of stock")
        return False

    # Charge only after the stock is secured. If payment fails, give the
    # reservation back so nothing is charged and nothing is delivered.
    if not await gateway.charge_once(order_id, quantity * price):
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
