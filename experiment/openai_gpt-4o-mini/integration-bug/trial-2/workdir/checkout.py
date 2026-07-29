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
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        return False

    available = await inventory.check_stock(quantity)
    if not available:
        await gateway.refund(order_id)
        print(f"Order {order_id}: out of stock, refund issued")
        return False

    decremented = await inventory.decrement(quantity)
    if not decremented:
        await gateway.refund(order_id)
        print(f"Order {order_id}: inventory error after payment — item not delivered, refund issued")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
