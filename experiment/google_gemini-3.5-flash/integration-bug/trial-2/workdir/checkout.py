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
    # Acquire lock to reserve inventory and prevent duplicate processing
    async with inventory.lock:
        if order_id in inventory.processed_orders:
            print(f"Order {order_id}: duplicate order request")
            return False

        inventory.processed_orders.add(order_id)

        # Decrement stock (reserve stock)
        decremented = await inventory.decrement(quantity)
        if not decremented:
            print(f"Order {order_id}: out of stock")
            inventory.processed_orders.remove(order_id)
            return False

    # Outside the lock, call payment gateway concurrently
    charged = False
    try:
        charged = await gateway.charge(order_id, quantity * price)
    except Exception as e:
        print(f"Order {order_id}: payment exception: {e}")
        charged = False

    if not charged:
        print(f"Order {order_id}: payment failed")
        # Release stock and remove from processed orders under lock
        async with inventory.lock:
            if order_id in inventory.processed_orders:
                inventory.processed_orders.remove(order_id)
            await inventory.increment(quantity)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
