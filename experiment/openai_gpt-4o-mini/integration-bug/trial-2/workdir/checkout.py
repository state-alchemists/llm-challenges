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
    available = await inventory.check_stock(quantity)

    if not available:
        print(f"Order {order_id}: out of stock.")
        return False

    # Charge order only if stock is confirmed first
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed.")
        return False

    # Ensure stock deductions post confirmation of charge
    success = await inventory.decrement(quantity)
    if not success:
        print(f"Order {order_id}: inventory error after payment — item not available.")
        return False

    print(f"Order {order_id}: SUCCESS.")
    return True