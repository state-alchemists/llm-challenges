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
    # Reserve stock first — atomic check-and-decrement under a lock.
    # This prevents overselling: if stock is insufficient, we bail immediately.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Charge the customer. If payment fails, restore the reserved stock
    # so no ghost charge remains and other orders can use the stock.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        await inventory.restore(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True