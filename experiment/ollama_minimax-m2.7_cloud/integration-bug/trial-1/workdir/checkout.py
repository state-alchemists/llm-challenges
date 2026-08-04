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
    # Atomically decrement inventory first — if this fails, out of stock.
    decremented = await inventory.atomic_decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # Inventory is now reserved. Charge the customer.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Refund inventory — the item is no longer reserved.
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Both inventory decremented and charge succeeded — order complete.
    print(f"Order {order_id}: SUCCESS")
    return True
