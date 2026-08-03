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
    # 1. Reserve stock first to prevent overselling
    # We use decrement as a "reserve" operation
    reserved = await inventory.decrement(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    try:
        # 2. Charge payment
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            # Release reserved stock if payment fails
            await inventory.increment(quantity)
            return False
        
        # 3. Order successful
        print(f"Order {order_id}: SUCCESS")
        return True
    except Exception as e:
        # 4. Recovery: If something crashes between charge and return, 
        # we must ensure we don't leave stock leaked or user charged without item.
        # In this specific simulation, the charge is the point of no return.
        # If charge succeeded but we crash, we refund.
        print(f"Order {order_id}: unexpected error {e}")
        # This is a simplification; in a real system we'd check if charge happened.
        # For this logic: if we are here, we likely didn't return True.
        # We attempt to undo the charge if possible or mark for manual review.
        # Since we don't have a robust transaction ID here, we'll just refund if we can.
        await gateway.refund(order_id, quantity * price)
        await inventory.increment(quantity)
        return False
