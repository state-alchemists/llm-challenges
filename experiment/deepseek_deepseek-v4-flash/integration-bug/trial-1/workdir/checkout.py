from inventory import Inventory
from payments import PaymentGateway


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # Reserve stock before charging: the atomic check-and-decrement guarantees
    # the item exists for this order before any money moves.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — put the reserved stock back; nothing was charged.
        await inventory.release(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Charge succeeded and the item is already reserved for this order.
    print(f"Order {order_id}: SUCCESS")
    return True
