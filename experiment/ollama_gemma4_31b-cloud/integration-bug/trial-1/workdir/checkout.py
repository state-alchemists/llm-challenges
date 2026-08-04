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
    # 1. Reserve stock first (pessimistic lock/decrement)
    # To prevent overselling, we must decrement stock BEFORE charging.
    # If the charge fails, we put the stock back.
    if not await inventory.decrement(quantity):
        print(f"Order {order_id}: out of stock")
        return False

    try:
        # 2. Charge the user
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            # Release stock back if payment fails
            await inventory.increment(quantity)
            return False
        
        print(f"Order {order_id}: SUCCESS")
        return True
    except Exception as e:
        # Ensure stock is returned on any unexpected error during charge
        await inventory.increment(quantity)
        print(f"Order {order_id}: unexpected error {e}")
        return False
