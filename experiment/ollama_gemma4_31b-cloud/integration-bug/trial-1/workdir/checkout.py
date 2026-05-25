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
    # 1. Atomic Reservation: try to secure the inventory first.
    # This prevents overselling and the "charge then fail to deliver" ghost charge scenario.
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    try:
        # 2. Payment: only charge if we have secured the stock.
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            # IMPORTANT: Restore inventory if payment fails.
            await inventory.increment(quantity)
            return False

        print(f"Order {order_id}: SUCCESS")
        return True
    except Exception as e:
        # 3. Failure Recovery: ensure inventory is restored if an unexpected error occurs after reservation.
        print(f"Order {order_id}: unexpected error {e}")
        await inventory.increment(quantity)
        return False
