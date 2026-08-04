from inventory import Inventory
from payments import PaymentGateway

async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
) -> bool:
    # Check if enough stock is available
    available = await inventory.check_stock(quantity)
    if not available:
        print(f"Order {order_id}: out of stock")
        return False

    # Proceed to charge the order only if not already charged
    if gateway.has_order(order_id):
        print(f"Order {order_id}: already charged")
        return False
    
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        return False

    # Decrement the inventory only after confirming charge
    decremented = await inventory.decrement(quantity)
    if not decremented:
        # If inventory decrement fails, cancel the charge (rollback)
        gateway.refund(order_id, quantity * price)  # Refund processing
        print(f"Order {order_id}: inventory error after payment — item not delivered")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
