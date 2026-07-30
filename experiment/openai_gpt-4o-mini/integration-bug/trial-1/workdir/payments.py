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
        if amount > 0:
            if not self.has_charged(order_id):
                self.charges.append({"order_id": order_id, "amount": amount})
        return True

    def has_charged(self, order_id: str) -> bool:
        return any(charge["order_id"] == order_id for charge in self.charges)