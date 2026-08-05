import asyncio
from inventory import Inventory
from payments import PaymentGateway

# Global lock to synchronize checkouts across the simulation.
# In a real distributed system, this would be a distributed lock (e.g., Redis).
_checkout_lock = asyncio.Lock()

async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    async with _checkout_lock:
        # 1. Atomic check and reserve.
        # We must check AND decrement within the same lock to prevent race conditions.
        available = await inventory.check_stock(quantity)
        if not available:
            print(f"Order {order_id}: out of stock")
            return False
        
        # Reserve stock immediately.
        decremented = await inventory.decrement(quantity)
        if not decremented:
            # This case should technically be unreachable with the lock, 
            # but kept for robustness.
            print(f"Order {order_id}: out of stock (race condition)")
            return False

        try:
            # 2. Payment.
            # We charge after reserving stock to ensure we have the item.
            charged = await gateway.charge(order_id, quantity * price)
            if not charged:
                print(f"Order {order_id}: payment failed")
                # Release stock if payment fails (Compensation).
                await inventory.increment(quantity)
                return False
            
            print(f"Order {order_id}: SUCCESS")
            return True

        except Exception as e:
            # Ensure stock is released if an unexpected error occurs during payment.
            await inventory.increment(quantity)
            print(f"Order {order_id}: unexpected error {e}")
            return False
