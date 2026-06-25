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
    # Atomically reserve inventory before charging
    reserved = await inventory.reserve(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        # Release reserved inventory since payment failed
        await inventory.release(quantity)
        print(f"Order {order_id}: payment failed")
        return False

    # Inventory already reserved and deducted; payment succeeded → item delivered
    print(f"Order {order_id}: SUCCESS")
    return True
