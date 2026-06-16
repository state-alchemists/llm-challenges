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
    # Reserve stock first — atomic decrement guarantees we never oversell.
    reserved = await inventory.decrement(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Now charge the customer. If payment fails, release the reservation.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed — stock released")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
