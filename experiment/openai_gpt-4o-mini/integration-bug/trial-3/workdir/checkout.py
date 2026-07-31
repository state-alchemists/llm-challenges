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

    if gateway.is_order_charged(order_id):
        print(f'Order {order_id}: already charged, skipping')
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if charged:
        print(f'Order {order_id}: Charge successful')
    print(f'Charge for order {order_id} was {'success' if charged else 'failure'}.')
    if not charged:
        print(f'Order {order_id}: payment failed')
        return False

    decremented = await inventory.decrement(quantity)

    charged = await gateway.charge(order_id, quantity * price)
    if charged:
        print(f'Order {order_id}: Charge successful')
    print(f'Charge for order {order_id} was {'success' if charged else 'failure'}.')

    if not charged:
        print(f"Order {order_id}: payment failed")
        return False

    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f'Order {order_id}: inventory error — item not delivered')
        return False
    if not decremented:
        print(f"Order {order_id}: inventory error after payment — item not delivered")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
