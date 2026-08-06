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
    # 1. Try to decrement inventory first (atomic operation)
    decremented = await inventory.try_decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock or failed to reserve")
        return False

    # 2. Attempt to charge the payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # 3. If payment fails, refund the inventory
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed, inventory refunded")
        return False

    # 4. Both inventory decremented and payment charged successfully
    print(f"Order {order_id}: SUCCESS")
    return True
