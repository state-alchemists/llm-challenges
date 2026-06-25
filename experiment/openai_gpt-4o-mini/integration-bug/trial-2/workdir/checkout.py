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
        print(f"Order {order_id}: out of stock")
        return False

    # Check if order ID has already been charged
    if order_id in gateway.get_charge_history():
        print(f"Order {order_id}: duplicate charge detected")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        return False

    # Only decrement stock if payment was successful
    if not await inventory.can_decrement(quantity):
        print(f"Order {order_id}: inventory error after payment — item not available")
        return False

    await inventory.decrement(quantity)
    print(f"Order {order_id}: SUCCESS")
    return True
