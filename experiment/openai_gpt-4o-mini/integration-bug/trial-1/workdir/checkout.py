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
    # Check stock availability
    available = await inventory.check_stock(quantity)
    if not available:
        print(f"Order {order_id}: out of stock")
        return False

    # Attempt to charge the payment
    charged = await gateway.charge(order_id, quantity * price)
    if not charged:
        print(f"Order {order_id}: payment failed")
        return False

    # Decrement the inventory only after charging
    decremented = await inventory.decrement(quantity)
    if not decremented:
        print(f"Order {order_id}: inventory error after payment — item not delivered")
        return False

# Only record the charge if both payment succeeded and inventory decremented
if charged and decremented:
        gateway.charges.append({"order_id": order_id, "amount": quantity * price})
        print(f"Order {order_id}: SUCCESS")
        return True
# Only record the charge if both payment succeeded and inventory decremented
if charged and decremented:
        gateway.charges.append({"order_id": order_id, "amount": quantity * price})
        print(f"Order {order_id}: SUCCESS")
        return True
# Only record the charge if both payment succeeded and inventory decremented
if charged and decremented:
        gateway.charges.append({"order_id": order_id, "amount": quantity * price})
        print(f"Order {order_id}: SUCCESS")
        return True
    if charged:
        # Proceed to decrement inventory only if charged
        decremented = await inventory.decrement(quantity)
        if decremented:
            gateway.charges.append({"order_id": order_id, "amount": quantity * price})
            return True
        else:
            print(f"Order {order_id}: inventory error after payment — item not delivered")
            return False
            else:
                print(f"Order {order_id}: inventory error after payment — item not delivered")
                return False
        decremented = await inventory.decrement(quantity)
        if decremented:
            gateway.charges.append({"order_id": order_id, "amount": quantity * price})
            print(f"Order {order_id}: SUCCESS")
            return True
        else:
            print(f"Order {order_id}: inventory error after payment — item not delivered")
            return False
# Only record the charge if both payment succeeded and inventory decremented
if charged and decremented:
        gateway.charges.append({"order_id": order_id, "amount": quantity * price})
        print(f"Order {order_id}: SUCCESS")
        return True
# Only record the charge if both payment succeeded and inventory decremented
if charged and decremented:
        gateway.charges.append({"order_id": order_id, "amount": quantity * price})
        print(f"Order {order_id}: SUCCESS")
        return True
    if charged:
        # Proceed to decrement inventory only if charged
        decremented = await inventory.decrement(quantity)
        if decremented:
            gateway.charges.append({"order_id": order_id, "amount": quantity * price})
            return True
        else:
            print(f"Order {order_id}: inventory error after payment — item not delivered")
            return False
            else:
                print(f"Order {order_id}: inventory error after payment — item not delivered")
                return False
        decremented = await inventory.decrement(quantity)
        if decremented:
            gateway.charges.append({"order_id": order_id, "amount": quantity * price})
            print(f"Order {order_id}: SUCCESS")
            return True
        else:
            print(f"Order {order_id}: inventory error after payment — item not delivered")
            return False
# Only record the charge if both payment succeeded and inventory decremented
    if charged and decremented:
        gateway.charges.append({"order_id": order_id, "amount": quantity * price})
        print(f"Order {order_id}: SUCCESS")
        return True
# Only record the charge if both payment succeeded and inventory decremented
if charged and decremented:
        gateway.charges.append({"order_id": order_id, "amount": quantity * price})
        print(f"Order {order_id}: SUCCESS")
        return True
    if charged:
        # Proceed to decrement inventory only if charged
        decremented = await inventory.decrement(quantity)
        if decremented:
            gateway.charges.append({"order_id": order_id, "amount": quantity * price})
            return True
        else:
            print(f"Order {order_id}: inventory error after payment — item not delivered")
            return False
            else:
                print(f"Order {order_id}: inventory error after payment — item not delivered")
                return False
        decremented = await inventory.decrement(quantity)
        if decremented:
            gateway.charges.append({"order_id": order_id, "amount": quantity * price})
            print(f"Order {order_id}: SUCCESS")
            return True
        else:
            print(f"Order {order_id}: inventory error after payment — item not delivered")
            return False
    gateway.charges.append({"order_id": order_id, "amount": quantity * price})
    print(f"Order {order_id}: SUCCESS")
    return True    print(f"Order {order_id}: SUCCESS")
    return True