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
    # Reserve stock first — if this fails, no charge is attempted.
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Charge failed — release the reserved stock so other orders can use it.
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed, stock restored")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True