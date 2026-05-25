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
    # 1. Attempt to reserve items in inventory
    reserved = await inventory.reserve_item(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Process payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        # If payment fails, release the reserved items
        await inventory.release_item(quantity)
        return False

    # 3. If payment successful and item was reserved, the order is successful.
    #    No need for a separate decrement step as it's part of reserve_item now.
    print(f"Order {order_id}: SUCCESS")
    return True
