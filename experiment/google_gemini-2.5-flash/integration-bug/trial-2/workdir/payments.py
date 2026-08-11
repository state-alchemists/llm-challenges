import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []

    async def refund(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.01)  # Simulate refund processing
        # Find and remove the charge
        for i, charge_record in enumerate(self.charges):
            if charge_record["order_id"] == order_id and charge_record["amount"] == amount:
                self.total_charged -= amount
                self.charges.pop(i)
                print(f"Order {order_id}: REFUNDED {amount}")
                return True
        print(f"Order {order_id}: REFUND FAILED (charge not found or amount mismatch)")
        return False

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        return True
