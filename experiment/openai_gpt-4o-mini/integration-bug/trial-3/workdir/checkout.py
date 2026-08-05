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
    reserved = await inventory.reserve(quantity)  # Reserve stock first
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)  # Attempt to charge
    if not charged:
        print(f"Order {order_id}: payment failed")
        await inventory.increment(quantity)  # Roll back reservation
        return False
        
    gateway.register_charge(order_id, quantity * price)  # Register the successful charge

    print(f"Order {order_id}: SUCCESS")
    return True
