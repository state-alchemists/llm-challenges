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
    # Check stock first
    available = await inventory.check_stock(quantity)
    if not available:
        print(f"Order {order_id}: out of stock")
        return False

    # Attempt to charge
    charge_amount = quantity * price
    charged = await gateway.charge(order_id, charge_amount)
    if not charged:
        print(f"Order {order_id}: payment failed or duplicate charge prevented")
        return False

    # Attempt to decrement inventory
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: inventory error after payment — item not delivered. Refunding...")
        await gateway.refund(order_id, charge_amount)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
