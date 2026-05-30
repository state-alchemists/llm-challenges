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
    # Reserve stock FIRST to prevent overselling
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    try:
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            # Release stock if payment fails
            await inventory.increment(quantity)
            return False

        print(f"Order {order_id}: SUCCESS")
        return True
    except Exception as e:
        # Ensure stock is returned if any unexpected error occurs during payment
        await inventory.increment(quantity)
        print(f"Order {order_id}: unexpected error {e}")
        return False
