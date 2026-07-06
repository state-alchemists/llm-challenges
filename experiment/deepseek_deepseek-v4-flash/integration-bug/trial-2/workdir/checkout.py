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
    # Step 1: Reserve inventory atomically (check + decrement, no await between them)
    # This is the critical section — under asyncio, no other coroutine can run
    # between the stock check and the decrement.
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    # Step 2: Charge the customer
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Payment failed — release the reservation
        await inventory.release(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Step 3: Success — order fulfilled
    print(f"Order {order_id}: SUCCESS")
    return True
