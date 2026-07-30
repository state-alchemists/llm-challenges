import asyncio
from inventory import Inventory
from payments import PaymentGateway
from contextlib import asynccontextmanager

@asynccontextmanager
async def acquire_lock(lock: asyncio.Lock):
    await lock.acquire()
    try:
        yield
    finally:
        lock.release()

lock = asyncio.Lock()

async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    async with acquire_lock(lock):
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
