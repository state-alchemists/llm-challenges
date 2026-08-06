import asyncio
from inventory import Inventory
from payments import PaymentGateway

_active_orders = set()
_charged_orders = set()


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    if order_id in _active_orders or order_id in _charged_orders:
        print(f"Order {order_id}: duplicate request ignored")
        return False

    _active_orders.add(order_id)
    reserved = False
    try:
        decremented = await inventory.decrement(quantity)
        if not decremented:
            print(f"Order {order_id}: out of stock")
            return False
        reserved = True

        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            return False

        _charged_orders.add(order_id)
        print(f"Order {order_id}: SUCCESS")
        return True
    except Exception as e:
        print(f"Order {order_id}: unexpected error: {e}")
        return False
    finally:
        if reserved and order_id not in _charged_orders:
            try:
                await asyncio.shield(inventory.increment(quantity))
            except Exception:
                pass
        _active_orders.discard(order_id)
