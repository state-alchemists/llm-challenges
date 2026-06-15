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
    # Attempt to reserve the item first
    reserved = await inventory.reserve_item(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed. Releasing reserved stock.")
        await inventory.increment(quantity)  # Release the reserved stock
        return False

    # If both reservation and charge are successful, the item is considered delivered.
    # The previous decrement call is no longer needed as reservation already decremented.
    print(f"Order {order_id}: SUCCESS")
    return True
