from inventory import Inventory
from payments import PaymentGateway


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # Reserve stock first — atomic check-and-decrement under lock.
    # This eliminates the TOCTOU race: no other coroutine can interleave
    # between "do we have stock?" and "take the stock."
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Stock is held; now try to charge.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release the reservation so other orders can use it.
        await inventory.release(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Payment succeeded and stock was already reserved — clean delivery.
    print(f"Order {order_id}: SUCCESS")
    return True
