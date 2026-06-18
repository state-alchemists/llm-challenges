from inventory import Inventory
from payments import PaymentGateway


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # Atomically reserve stock — no TOCTOU race
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Stock is reserved; charge the customer
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release the reservation
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed, stock restored")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
