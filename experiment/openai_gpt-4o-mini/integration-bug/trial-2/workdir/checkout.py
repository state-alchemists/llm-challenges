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
    # Attempt to decrement inventory first
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: inventory error — item not delivered")
        return False

    # Now charge the customer
    charged = await gateway.charge(order_id, quantity * price)
    print(f"Order {order_id}: charge successful? {charged}")

    if not charged:
        print(f"Order {order_id}: payment failed")
        await inventory.increment(quantity)  # Rollback inventory on payment failure
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
