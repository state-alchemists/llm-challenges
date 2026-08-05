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
    # Try to reserve stock first (atomic check and decrement)
    reserved = await inventory.try_reserve_stock(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock or reservation failed")
        return False

    # Attempt to charge the customer
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed. Releasing reserved stock.")
        await inventory.release_stock(quantity) # Release stock if payment fails
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
