import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self.successful_charges: set[str] = set() # To track successfully charged order_ids for idempotency

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)

        if order_id in self.successful_charges:
            print(f"PaymentGateway: Order {order_id} already successfully charged (idempotent).")
            return True

        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self.successful_charges.add(order_id)
        return True

    async def refund(self, order_id: str, amount: float) -> None:
        await asyncio.sleep(0.01) # Simulate async refund process
        # Remove the charge from total_charged and charges list
        # This assumes a simple model where we can just subtract and remove
        # In a real system, a more robust transaction reversal would be needed
        if order_id in self.successful_charges:
            self.total_charged -= amount
            self.charges = [charge for charge in self.charges if charge["order_id"] != order_id]
            self.successful_charges.remove(order_id)
            print(f"PaymentGateway: Refunded order {order_id} for ${amount:.2f}")
        else:
            print(f"PaymentGateway: No successful charge found for order {order_id} to refund.")
