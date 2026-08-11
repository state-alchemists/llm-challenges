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

    try:
        # First, reserve the stock
        decremented = await inventory.decrement(quantity)
        if not decremented:
            print(f"Order {order_id}: out of stock")
            return False

        try:
            charged = await gateway.charge(order_id, quantity * price)
        except Exception as e:
            # If charging raises an exception, we must release the reserved stock
            try:
                await inventory.increment(quantity)
            except Exception as inc_err:
                print(f"Order {order_id}: failed to release stock after charge error: {inc_err}")
            print(f"Order {order_id}: payment failed with error: {e}")
            raise e

        if not charged:
            # If charging failed, we must release the reserved stock
            try:
                await inventory.increment(quantity)
            except Exception as inc_err:
                print(f"Order {order_id}: failed to release stock after payment failure: {inc_err}")
            print(f"Order {order_id}: payment failed")
            return False

        _charged_orders.add(order_id)
        print(f"Order {order_id}: SUCCESS")
        return True
    finally:
        _active_orders.discard(order_id)
