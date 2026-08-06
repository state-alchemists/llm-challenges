import asyncio
from inventory import Inventory
from payments import PaymentGateway


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
    order_lock: asyncio.Lock | None = None,
) -> bool:
    if order_lock is None:
        order_lock = asyncio.Lock()

    print(f"Order {order_id}: acquiring lock")
    async with order_lock:
        print(f"Order {order_id}: lock acquired")
        decremented = await inventory.atomic_check_decrement(quantity)
        if not decremented:
            print(f"Order {order_id}: out of stock")
            return False

        print(f"Order {order_id}: stock decremented, charging ${quantity * price}")
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed — refunding")
            await gateway.refund(order_id, quantity * price)
            await inventory.atomic_increment(quantity)
            return False

    print(f"Order {order_id}: SUCCESS")
    return True
