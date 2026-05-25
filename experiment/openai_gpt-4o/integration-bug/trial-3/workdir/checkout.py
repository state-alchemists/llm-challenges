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
    # Attempt to decrement inventory first, ensuring stock is reserved.
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # Charge the payment after confirming inventory.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        # Compensate by incrementing back the stock since charge failed
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
