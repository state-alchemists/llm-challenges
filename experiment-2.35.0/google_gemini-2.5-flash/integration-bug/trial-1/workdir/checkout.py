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
    reserved = await inventory.reserve_stock(quantity)
    if not reserved:
        print(f"Order {order_id}: out of stock")
        return False

    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed, releasing stock")
        await inventory.release_stock(quantity)
        return False

    # Stock is already reserved and decremented by reserve_stock,
    # so we just confirm the order now. If a critical error occurs here,
    # we need to refund the charge.
    try:
        # In a real system, there might be other steps here that could fail.
        # For this simulation, we consider the reservation as the "delivery".
        pass
    except Exception as e:
        print(f"Order {order_id}: critical error after payment and stock reservation: {e}, refunding charge")
        await gateway.refund(order_id, quantity * price)
        await inventory.release_stock(quantity) # Release stock in case of a conceptual "delivery" failure after reservation
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
