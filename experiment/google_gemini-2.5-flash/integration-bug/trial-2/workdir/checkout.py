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
        # Refund the customer if inventory decrement fails after payment
        await gateway.refund(order_id, quantity * price)
        print(f"Order {order_id}: refunded due to inventory error")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
