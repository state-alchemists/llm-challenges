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
    # Reserve stock atomically (decrement under lock)
    reserved = await inventory.decrement(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Charge the customer
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Rollback: release reserved stock
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed — stock released")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True