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
    # To prevent overselling and ghost charges, we must ensure
    # that stock is reserved before payment is attempted.
    # If payment fails, we release the stock.
    # If payment succeeds but stock decrement fails (which shouldn't happen if reserved),
    # we must refund or handle the error.

    # 1. Try to reserve/decrement stock first (Atomic check-and-set)
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Attempt payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        # Restore stock since payment failed
        await inventory.increment(quantity)
        return False

    # Since we decremented stock BEFORE payment, and payment succeeded,
    # the order is now successful.
    print(f"Order {order_id}: SUCCESS")
    return True
