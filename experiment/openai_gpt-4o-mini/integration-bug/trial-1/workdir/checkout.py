import asyncio
from inventory import Inventory
from payments import PaymentGateway

async def checkout(
    lock: asyncio.Lock,
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    async with lock:
        available = await inventory.check_stock(quantity)
        if not available:
            print(f"Order {order_id}: out of stock")
            return False

        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed or order already processed")
            return False

        try:
            await inventory.decrement(quantity)
        except Exception as e:
            print(f"Order {order_id}: inventory error — {str(e)}")
            return False

        print(f"Order {order_id}: SUCCESS")
        return True