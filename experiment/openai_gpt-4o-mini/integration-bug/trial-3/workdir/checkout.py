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
    # Check stock
    async with inventory.lock:  # Acquire lock for inventory checks
        available = await inventory.check_stock(quantity)
        if not available:
            print(f"Order {order_id}: out of stock")
            return False

        # Charge payment
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            return False
            
        # Decrement inventory
        if not await inventory.decrement(quantity):
            print(f"Order {order_id}: inventory error after successful charge — item not delivered")
            return False

    print(f"Order {order_id}: SUCCESS")
    return True