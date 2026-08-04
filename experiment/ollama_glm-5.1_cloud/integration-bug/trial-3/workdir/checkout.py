from inventory import Inventory
from payments import PaymentGateway


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # Reserve stock atomically before any async work.
    # reserve() is synchronous — no await, so no interleaving under asyncio.
    if not inventory.reserve(quantity):
        print(f"Order {order_id}: out of stock")
        return False

    # Stock is reserved; now attempt payment.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release the reserved stock.
        inventory.release(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True