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
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    success = False
    try:
        charged = await gateway.charge(order_id, quantity * price)
        if charged:
            success = True
            print(f"Order {order_id}: SUCCESS")
            return True
        else:
            print(f"Order {order_id}: payment failed")
            return False
    finally:
        if not success:
            await inventory.increment(quantity)
