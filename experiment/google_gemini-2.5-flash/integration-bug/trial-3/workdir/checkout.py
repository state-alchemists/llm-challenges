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
    # Atomically check stock and reserve item
    reserved = await inventory.reserve_item(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        await inventory.increment(quantity)  # Release the reserved item
        return False

    # If we get here, payment was successful and inventory was reserved.
    # The item is considered delivered.

    print(f"Order {order_id}: SUCCESS")
    return True
