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
    # 1. Reserve stock atomically (check + decrement under lock).
    #    No race: only one coroutine can decrement at a time.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # 2. Charge the customer.  Stock is already reserved so no
    #    other coroutine can oversell these units.
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release the reserved stock so others can buy it.
        await inventory.release(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # 3. Both reservation and charge succeeded — item is delivered.
    #    Stock was already decremented in step 1.
    print(f"Order {order_id}: SUCCESS")
    return True