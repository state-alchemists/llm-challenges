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
    # Use the atomic decrement for inventory to prevent overselling
    # The stock check is now part of the atomic decrement operation.

    # First, attempt to charge the customer.
    amount_to_charge = quantity * price
    charged = await gateway.charge(order_id, amount_to_charge)

    if not charged:
        print(f"Order {order_id}: payment failed")
        return False

    # If payment is successful, try to decrement inventory atomically.
    decremented = await inventory._atomic_decrement(quantity)

    if not decremented:
        # If inventory decrement fails, refund the charge to prevent ghost charges.
        print(f"Order {order_id}: inventory error after payment — item not delivered. Initiating refund.")
        refunded = await gateway.refund(order_id, amount_to_charge)
        if refunded:
            print(f"Order {order_id}: refund successful.")
        else:
            print(f"Order {order_id}: CRITICAL ERROR - refund failed! Manual intervention needed.")
        return False

    print(f"Order {order_id}: SUCCESS")
    return True
