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
    # Attempt to decrement and charge
    stock_available = await inventory.check_stock(quantity)
    if not stock_available:
        print(f"Order {order_id}: out of stock")
        return False

    # Attempt to charge payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: cannot fulfill order or payment failed")
        return False
    if not charged:
        print(f"Order {order_id}: cannot fulfill order or payment failed")
        return False

        print(f"Order {order_id}: out of stock")
        return False

    # Attempt to charge payment
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
