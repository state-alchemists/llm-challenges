import asyncio
from inventory import Inventory
from payments import PaymentGateway

_processed_orders: set = set()


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    global _processed_orders

    # Idempotency: reject if this order_id was already successfully processed
    if order_id in _processed_orders:
        print(f"Order {order_id}: duplicate order")
        return False

    # Decrement inventory FIRST — this is atomic and prevents overselling
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # Payment only after confirmed inventory reservation
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — restore inventory since we haven't delivered anything
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed, inventory restored")
        return False

    # Mark order as successfully processed
    _processed_orders.add(order_id)
    print(f"Order {order_id}: SUCCESS")
    return True