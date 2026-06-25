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
    # 1. Atomically reserve inventory before charging.
    #    This eliminates the TOCTOU race between check_stock and decrement.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Charge the customer. If payment fails, roll back the reservation
    #    so stock is returned and no ghost charge remains.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed — inventory released")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True