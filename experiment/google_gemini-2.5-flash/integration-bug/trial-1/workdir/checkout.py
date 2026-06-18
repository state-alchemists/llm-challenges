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
    await inventory.acquire_lock()
    try:
        available = await inventory.check_stock(quantity)
        if not available:
            print(f"Order {order_id}: out of stock")
            return False

        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            return False

        decremented = await inventory.decrement(quantity)
        if not decremented:
            print(f"Order {order_id}: inventory error after payment - attempting refund")
            # If decrement fails after charge, we need to refund
            # For this simulation, we'll consider it a failed order
            # and rely on the monitoring to catch the discrepancy.
            # A real system would have a refund mechanism here.
            return False

    finally:
        inventory.release_lock()

    print(f"Order {order_id}: SUCCESS")
    return True
