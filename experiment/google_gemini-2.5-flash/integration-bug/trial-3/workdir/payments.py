import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        return True

    async def refund(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.01)
        # In a real system, you'd integrate with a payment provider's refund API.
        # For this mock, we'll remove the charge and adjust the total.
        for i, charge in enumerate(self.charges):
            if charge["order_id"] == order_id and charge["amount"] == amount:
                self.charges.pop(i)
                self.total_charged -= amount
                print(f"Order {order_id}: REFUNDED ${amount:.2f}")
                return True
        return False
