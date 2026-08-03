from inventory import Inventory
from payments import PaymentGateway


async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # Reserve the stock atomically BEFORE charging. An order is only charged
    # once the item is guaranteed to be ours, which closes both races in the
    # original flow:
    #   - overselling: check_stock and decrement were separate await points,
    #     so concurrent orders all passed the check before any decremented;
    #   - ghost charges: charging happened before delivery, and a decrement
    #     that failed left the customer billed with no item delivered.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed: give the reserved stock back so another order can take it.
        await inventory.increment(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
