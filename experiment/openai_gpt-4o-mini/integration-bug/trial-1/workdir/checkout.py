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

    charged = await gateway.charge(order_id, quantity * price)
    if charged:
        # Try to decrement inventory only if charged
        decremented = await inventory.decrement_if_available(quantity)
        if not decremented:
            print(f"Order {order_id}: inventory error after payment — item not delivered")
            return False
        # Record the charge
        gateway.charges.append({"order_id": order_id, "amount": quantity * price})
    else:
        print(f"Order {order_id}: payment failed")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True