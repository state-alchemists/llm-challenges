import asyncio
from inventory import Inventory
from payments import PaymentGateway

_checkout_lock = asyncio.Lock()


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # Atomically reserve stock: check AND decrement under lock
    reserved = await inventory.reserve_stock(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Stock is reserved — customer must be charged
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Refund: release the reserved stock since payment failed
        await inventory.release_stock(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
