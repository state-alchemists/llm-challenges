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
    available = await inventory.check_stock(quantity)
    if not available:
        print(f"Order {order_id}: out of stock")
        return False

    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False
    charged = await gateway.charge(order_id, quantity * price)
    print(f"Order {order_id}: charged status = {charged}")
    if not charged:
        print(f"Order {order_id}: payment failed")
        return False
    # Only decrement inventory upon successful charge
    if charged:
        # Ensure there is stock before decrementing
        if not await inventory.check_stock(quantity):
            print(f"Order {order_id}: out of stock after payment")
            return False
        await inventory.decrement(quantity)
        print(f"Order {order_id}: SUCCESS")
        return True
    else:
        print(f"Order {order_id}: payment failed")
        return False
        print(f"Order {order_id}: inventory error after payment — item not delivered")
        return False
        print(f"Order {order_id}: inventory error after payment — item not delivered")
        return False
    print(f"Order {order_id}: SUCCESS")
    return True

    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: inventory error after payment — item not delivered")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
