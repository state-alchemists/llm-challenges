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
    # Atomically reserve stock (check + decrement under lock).
    # This prevents overselling by serialising all inventory operations.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Stock is now held for this order. Try to charge.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release the reservation so other orders can use it.
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed, stock released")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
