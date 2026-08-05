import asyncio
from inventory import Inventory
from payments import PaymentGateway

_order_locks = {}

async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    lock = _order_locks.setdefault(order_id, asyncio.Lock())
    
    async with lock:
        # Check if this order has already been successfully charged
        already_charged = any(c["order_id"] == order_id for c in gateway.charges)
        if already_charged:
            print(f"Order {order_id}: already successfully processed")
            return False

        decremented = await inventory.decrement(quantity)
        if not decremented:
            print(f"Order {order_id}: out of stock")
            return False

        try:
            charged = await gateway.charge(order_id, quantity * price)
        except Exception:
            await inventory.increment(quantity)
            raise

        if not charged:
            print(f"Order {order_id}: payment failed")
            await inventory.increment(quantity)
            return False

        print(f"Order {order_id}: SUCCESS")
        return True
