import asyncio
from inventory import Inventory
from payments import PaymentGateway

_locks = {}

async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    inv_id = id(inventory)
    if inv_id not in _locks:
        _locks[inv_id] = asyncio.Lock()
    lock = _locks[inv_id]

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
