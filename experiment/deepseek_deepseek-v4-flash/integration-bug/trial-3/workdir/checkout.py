from inventory import Inventory
from payments import PaymentGateway


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # Reserve stock FIRST. Only when an item is actually ours to deliver
    # do we charge; there is no window in which many orders pass a stock
    # check and then oversell, and no path that charges for an item we
    # cannot deliver.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge_once(order_id, quantity * price)
    if not charged:
        # Payment failed (or this order was already charged elsewhere):
        # give the reserved stock back so no item is lost.
        await inventory.release(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
