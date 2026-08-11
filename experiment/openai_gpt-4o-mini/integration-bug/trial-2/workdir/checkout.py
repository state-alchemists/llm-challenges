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
    # Check stock availability before processing the order
    if not await inventory.check_stock(quantity):
        print(f"Order {order_id}: out of stock")
        return False

    # Attempt to charge 
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed, aborting delivery")
        return False

    # Decrement stock after successful charge
    reserved = await inventory.decrement(quantity)
    if not reserved:
        print(f"Order {order_id}: inventory decrement failed")
        # Rollback payment since inventory could not be decremented
        await gateway.refund(order_id, quantity * price)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True