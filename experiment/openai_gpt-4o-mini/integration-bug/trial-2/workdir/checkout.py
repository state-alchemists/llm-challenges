import asyncio
from inventory import Inventory
from payments import PaymentGateway

async def checkout(
    order_id: str,
    quantity: int,
    price: float,
    inventory: Inventory,
    gateway: PaymentGateway,
    processed_orders: set
) -> bool:
    if order_id in processed_orders:
        print(f"Order {order_id}: already processed.")
        return False

    # Check inventory and handle decrement atomically
    if not await inventory.check_stock(quantity):
        print(f"Order {order_id}: out of stock")
        return False

    # Lock inventory during the transaction
    can_decrement = await inventory.update_stock(quantity)
    if not can_decrement:
        print(f"Order {order_id}: inventory cannot be decremented")
        return False

    # Process payment only if inventory decrement was successful
    charged = await gateway.charge(order_id, price * quantity)  # charge accurate price
    if not charged:
        await inventory.increment(quantity)  # Restore stock if payment fails
        print(f"Order {order_id}: payment failed")
        return False

    processed_orders.add(order_id)  # Mark order as processed

    print(f"Order {order_id}: SUCCESS")
    return True
