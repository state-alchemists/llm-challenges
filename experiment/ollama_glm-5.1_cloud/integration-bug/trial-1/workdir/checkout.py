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
    # Phase 1: Atomically reserve stock (no TOCTOU gap).
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Phase 2: Charge the customer.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Rollback: release the reserved stock.
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Charge succeeded; reservation is now a committed sale.
    print(f"Order {order_id}: SUCCESS")
    return True