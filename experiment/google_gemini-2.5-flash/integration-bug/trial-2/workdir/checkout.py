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
    # Try to decrement stock first (atomic operation)
    decremented = await inventory.try_decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # If stock is reserved, proceed with payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed, increment stock back (rollback)
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed, stock rolled back")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
