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
    # Reserve the items first: a charge is only made once the stock is
    # guaranteed, so the order can never oversell or charge without delivery.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    try:
        charged = await gateway.charge(order_id, quantity * price)
    except Exception:
        # Unexpected payment error — give the reserved items back.
        await inventory.release(quantity)
        raise

    if not charged:
        await inventory.release(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
