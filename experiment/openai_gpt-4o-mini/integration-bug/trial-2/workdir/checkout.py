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
    # New async lock
    async with inventory.lock:
        available = await inventory.check_stock(quantity)
        if not available:
            print(f"Order {order_id}: out of stock")
            return False
        
        # Deduct stock first before charging
        decrement_successful = await inventory.decrement(quantity)
        if not decrement_successful:  # This check should be redundant now
            print(f"Order {order_id}: inventory error - unable to decrement stock")
            return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Rollback the inventory if charge fails
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed, inventory rolled back")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
