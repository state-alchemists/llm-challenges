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

    # Attempt to charge the payment first
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        return False

    # Now check the availability of stock
    available = await inventory.check_stock(quantity)
    if not available:
        print(f"Order {order_id}: out of stock after payment — refunding charge")
        # Refund charge simulated here
        gateway.total_charged -= quantity * price  # Simulated refund
        return False

    # Decrement the inventory
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: inventory error after payment — item not delivered, refunding charge")
        gateway.total_charged -= quantity * price  # Refund again if decrement fails
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
