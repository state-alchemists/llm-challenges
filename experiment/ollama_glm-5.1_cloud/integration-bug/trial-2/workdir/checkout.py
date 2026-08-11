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
    # Reserve inventory atomically before attempting payment.
    # This prevents overselling (stock never goes below zero) and
    # eliminates the ghost-charge window where payment succeeds but
    # inventory can't deliver.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release the reserved stock so others can buy it.
        await inventory.release(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Inventory was already decremented during reserve; the order is complete.
    print(f"Order {order_id}: SUCCESS")
    return True
