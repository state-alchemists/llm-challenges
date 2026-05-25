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
    async with inventory.lock:
        if not hasattr(gateway, "_charged_orders"):
            gateway._charged_orders = set()
        if order_id in gateway._charged_orders:
            print(f"Order {order_id}: already processed")
            return False

        available = await inventory.check_stock(quantity)
        if not available:
            print(f"Order {order_id}: out of stock")
            return False

        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            return False

        gateway._charged_orders.add(order_id)

        decremented = await inventory.decrement(quantity)
        if not decremented:
            print(f"Order {order_id}: inventory error after payment — item not delivered")
            return False

        print(f"Order {order_id}: SUCCESS")
        return True
