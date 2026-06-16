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
    # Use the lock on the inventory to serialize the checkout flow, preventing
    # race conditions such as ghost charges and overselling.
    lock = getattr(inventory, "_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        try:
            inventory._lock = lock
        except AttributeError:
            pass

    async with lock:
        available = await inventory.check_stock(quantity)
        if not available:
            print(f"Order {order_id}: out of stock")
            return False

        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            return False

        decremented = await inventory.decrement(quantity)
        if not decremented:
            print(f"Order {order_id}: inventory error after payment — item not delivered")
            return False

        print(f"Order {order_id}: SUCCESS")
        return True
