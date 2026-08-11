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
    # Try to decrement stock atomically first
    decremented = await inventory.try_decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock or inventory lock contention")
        return False

    # Attempt to charge
    amount = quantity * price
    charged = await gateway.charge(order_id, amount)
    if not charged:
        # Payment failed, increment stock back (rollback)
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed, stock rolled back")
        return False

    # Payment succeeded and stock decremented, order is successful
    print(f"Order {order_id}: SUCCESS")
    return True
