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
    # Reserve stock atomically BEFORE charging, so every successful payment
    # has an item set aside and stock can never be oversold.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed: give the stock back so it can be sold to someone else.
        await inventory.release(quantity)
        print(f"Order {order_id}: payment failed — stock released")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
