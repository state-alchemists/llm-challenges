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
    # Reserve stock first to prevent overselling and ghost charges
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    try:
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            print(f"Order {order_id}: payment failed")
            # Release stock on payment failure
            await inventory.increment(quantity)
            return False
    except Exception as e:
        print(f"Order {order_id}: unexpected payment error {e}")
        await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
