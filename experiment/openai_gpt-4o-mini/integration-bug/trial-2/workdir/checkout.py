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
    print(f"Processing order {order_id}.")
    available = await inventory.check_stock(quantity)
    if not available:
        print(f"Order {order_id}: out of stock")
        return False

    # Ensure to check charge status before inventory decrements
    if await gateway.has_charged(order_id):
        print(f"Order {order_id}: already charged, skipping charge.")
        return False

    # Attempt to decrement the inventory
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: inventory error before charging — item not delivered")
        return False

    print(f"Order {order_id}: attempting to charge.")
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        await inventory.increment(quantity)  # Restore stock if charge fails
        print(f"Order {order_id}: payment failed. Restoring inventory.")
        return False

    print(f"Order {order_id}: SUCCESS")
    gateway.charges.append({"order_id": order_id, "amount": quantity * price})  # Mark as charged
    return True