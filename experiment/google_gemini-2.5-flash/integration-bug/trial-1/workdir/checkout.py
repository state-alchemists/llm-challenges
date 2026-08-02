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
    charge_amount = quantity * price
    charged = await gateway.charge(order_id, charge_amount)
    if not charged:
        print(f"Order {order_id}: payment failed or already processed")
        return False

    decremented = False
    try:
        decremented = await inventory.try_decrement(quantity)
        if not decremented:
            print(f"Order {order_id}: out of stock or inventory error after payment")
            return False
    finally:
        if charged and not decremented:
            # If payment succeeded but inventory decrement failed, refund the charge.
            await gateway.refund(order_id, charge_amount)

    print(f"Order {order_id}: SUCCESS")
    return True
