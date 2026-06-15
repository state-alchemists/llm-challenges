from inventory import Inventory
from payments import PaymentGateway


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # Reserve stock atomically before any payment — this is the single
    # point of truth for availability. If it fails, no charge is made.
    if not await inventory.reserve(quantity):
        print(f"Order {order_id}: out of stock")
        return False

    # Stock is secured. Now attempt payment.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release the reserved stock so others can use it.
        await inventory.release(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Both stock and payment secured. Order is complete.
    print(f"Order {order_id}: SUCCESS")
    return True
