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
    # No explicit stock check needed; inventory.decrement handles atomicity.

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed or already charged")
        return False

    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: inventory error after payment — initiating refund")
        await gateway.refund(order_id, quantity * price)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
