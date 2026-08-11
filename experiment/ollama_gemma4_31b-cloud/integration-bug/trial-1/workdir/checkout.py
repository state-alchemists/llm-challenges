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
    # 1. Atomic Stock Reservation
    # To prevent ghost charges, we must ensure we HAVE the stock before charging.
    # We decrement first, then charge. If charge fails, we increment back.
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    try:
        # 2. Charge Payment
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            await inventory.increment(quantity)
            return False

        print(f"Order {order_id}: SUCCESS")
        return True
    except Exception as e:
        print(f"Order {order_id}: unexpected error {e}")
        await inventory.increment(quantity)
        return False
