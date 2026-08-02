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
    # Atomically check and decrement stock
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock or inventory error")
        return False

    # Proceed with payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # If payment fails, increment stock back to prevent ghost charges
        print(f"Order {order_id}: payment failed, restocking item(s)")
        await inventory.increment(quantity)
        await gateway.refund(order_id, quantity * price) # Ensure no partial charges remain
        return False

    # If both succeed, the order is complete
    print(f"Order {order_id}: SUCCESS")
    return True
