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
    # Reserve inventory first — atomic check-and-decrement under lock
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # Charge only after inventory is secured
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Roll back — release the reserved inventory
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True