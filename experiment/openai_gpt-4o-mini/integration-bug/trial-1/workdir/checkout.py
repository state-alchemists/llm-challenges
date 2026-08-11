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
    if gateway.is_order_charged(order_id):
        print(f"Order {order_id}: already charged")
        return False

    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        await inventory.release(quantity)  # Release if payment fails
        print(f"Order {order_id}: payment failed")
        return False

    decremented = await inventory.decrement(quantity)
    if not decremented:
        await inventory.release(quantity)  # Release if decrement fails
        print(f"Order {order_id}: inventory error after payment — item not delivered")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True