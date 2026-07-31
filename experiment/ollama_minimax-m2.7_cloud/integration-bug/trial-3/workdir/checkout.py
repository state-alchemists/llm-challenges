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
    # Reserve inventory first (atomic — no race between check and decrement)
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Attempt charge after successful reservation
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Rollback: release reserved inventory
        await inventory.release(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # No further action needed — inventory already decremented on reserve
    print(f"Order {order_id}: SUCCESS")
    return True
