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
    # Reserve stock atomically BEFORE charging. If the reservation succeeds,
    # the item is already set aside for this order, so a later successful
    # charge can never be a ghost charge (paid but undelivered).
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge_once(order_id, quantity * price)
    if not charged:
        # Payment failed: give the reserved stock back so it can be sold to
        # another customer.
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
