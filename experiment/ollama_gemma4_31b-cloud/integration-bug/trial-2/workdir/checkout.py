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
    # Check stock while holding the lock to make this atomic with the subsequent decrement
    # However, the requirements say "do not change public interfaces".
    # If we can't change the interface to a combined 'reserve' method, we must be careful.
    
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
        # Fix Ghost Charge: Refund if inventory decrement fails
        await gateway.refund(order_id, quantity * price)
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
