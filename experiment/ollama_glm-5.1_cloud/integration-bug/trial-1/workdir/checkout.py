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
    # Reserve stock atomically before attempting payment.
    # This prevents overselling: only orders that hold a reservation
    # can proceed to charge, and stock is guaranteed not to go below zero.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Attempt payment. If it fails, release the reserved stock.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed — stock released")
        return False

    # Stock was already decremented by reserve(); charge succeeded.
    print(f"Order {order_id}: SUCCESS")
    return True