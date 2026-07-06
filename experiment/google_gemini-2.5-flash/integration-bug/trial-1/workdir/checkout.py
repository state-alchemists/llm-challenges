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
    # First, check stock and decrement it atomically
    stock_reserved = await inventory.decrement(quantity)
    if not stock_reserved:
        print(f"Order {order_id}: out of stock or inventory error during reservation")
        return False

    # Attempt to charge the customer
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # If payment fails, we need to return the reserved stock
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed, stock returned")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
