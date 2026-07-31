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
    # Check for stock availability
    available = await inventory.check_stock(quantity)
    if not available:
        print(f"Order {order_id}: out of stock")
        return False

    # Try to decrement inventory
    decremented = await inventory.decrement(quantity)
    print(f"Order {order_id}: inventory decrement result: {decremented}")
    print(f"Order {order_id}: stock after decrement: {inventory.stock}")

    if not decremented:
        print(f"Order {order_id}: inventory error — item not delivered")
        return False

    # Charge the payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed after successful inventory decrement")
        await inventory.increment(quantity)  # Restore stock if charge fails
        return False  

    print(f"Order {order_id}: SUCCESS")
    return True
