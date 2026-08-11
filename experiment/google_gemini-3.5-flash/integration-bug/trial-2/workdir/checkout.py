import asyncio
from inventory import Inventory
from payments import PaymentGateway


_active_orders = set()


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    if order_id in _active_orders:
        print(f"Order {order_id}: already processing")
        return False

    if hasattr(gateway, "charges") and any(
        c["order_id"] == order_id for c in gateway.charges
    ):
        print(f"Order {order_id}: already charged")
        return False

    _active_orders.add(order_id)
    charged = False
    decremented = False
    try:
        decremented = await inventory.decrement(quantity)
        if not decremented:
            print(f"Order {order_id}: out of stock")
            return False

        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            return False

        print(f"Order {order_id}: SUCCESS")
        return True
    finally:
        _active_orders.discard(order_id)
        if decremented and not charged:
            await asyncio.shield(inventory.increment(quantity))
