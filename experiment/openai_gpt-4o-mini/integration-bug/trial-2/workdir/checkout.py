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
    # Start a lock for the inventory
    await inventory.lock()
    available = await inventory.check_stock(quantity)
    if not available:
        print(f"Order {order_id}: out of stock")
        await inventory.unlock()
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        await inventory.unlock()
        return False

    decremented = await inventory.decrement(quantity)
    if not decremented:
        await gateway.refund(order_id)  # Refund payment on inventory error
        print(f"Order {order_id}: inventory error after payment — item not delivered")
        await inventory.unlock()
        return False

    print(f"Order {order_id}: SUCCESS")
    await inventory.unlock()
    return True
    available = await inventory.check_stock(quantity)
    if not available:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        return False

    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: inventory error after payment — item not delivered")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
