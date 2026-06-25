from inventory import Inventory
from payments import PaymentGateway


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # Atomically reserve inventory before attempting payment.
    # This prevents overselling (no two concurrent orders can reserve the same item).
    reserved = await inventory.try_reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Now attempt payment. If it fails, release the reservation.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        await inventory.release_reservation(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Payment succeeded and inventory is already decremented — guaranteed delivery.
    print(f"Order {order_id}: SUCCESS")
    return True
