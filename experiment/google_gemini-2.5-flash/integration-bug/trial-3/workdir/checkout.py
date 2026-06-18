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
    # Try to reserve stock first (acquires inventory lock)
    reserved = await inventory.reserve_and_decrement(order_id, quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock or already reserved")
        return False

    # Attempt to charge (acquires payment gateway lock)
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed. Releasing reserved stock.")
        await inventory.release_reserved_stock(order_id, quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
