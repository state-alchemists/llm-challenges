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
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        return False

    # Only try to decrement inventory after a successful charge
    decremented = await inventory.try_decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: inventory error after payment — item not delivered. Refunding.")
        await gateway.refund(order_id)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
