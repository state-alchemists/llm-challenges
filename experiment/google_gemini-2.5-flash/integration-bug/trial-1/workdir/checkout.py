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
    # 1. Try to reserve stock
    reserved = await inventory.reserve_stock(order_id, quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Attempt to charge
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed, releasing stock")
        await inventory.release_stock(order_id)  # Release reserved stock on payment failure
        return False

    # 3. Payment successful, confirm reservation (which means the stock decrement is final)
    await inventory.confirm_reservation(order_id)

    print(f"Order {order_id}: SUCCESS")
    return True
