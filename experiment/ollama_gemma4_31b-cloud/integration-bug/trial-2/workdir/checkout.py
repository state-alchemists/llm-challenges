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
    # Use a lock to prevent race conditions during stock check and decrement
    async with inventory.lock:
        available = await inventory.check_stock(quantity)
        if not available:
            print(f"Order {order_id}: out of stock")
            return False

        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            return False

        decremented = await inventory.decrement(quantity)
        if not decremented:
            # This case is now virtually impossible with the lock, 
            # but we keep it for robustness and refund the user.
            print(f"Order {order_id}: inventory error after payment — item not delivered")
            await gateway.refund(order_id, quantity * price)
            return False

        print(f"Order {order_id}: SUCCESS")
        return True
