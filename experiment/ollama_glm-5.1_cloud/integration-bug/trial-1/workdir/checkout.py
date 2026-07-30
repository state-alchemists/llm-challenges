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
    # Reserve stock first — this is atomic in asyncio (no await between check & decrement)
    reserved = await inventory.decrement(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Attempt payment on the reserved stock
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release the reservation so others can buy
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
