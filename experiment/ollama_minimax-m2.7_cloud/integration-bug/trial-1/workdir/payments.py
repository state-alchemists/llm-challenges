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
        if order_id in {c["order_id"] for c in self.charges}:
            return False
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        return True

    async def refund(self, order_id: str) -> bool:
        await asyncio.sleep(0.01)
        for i, c in enumerate(self.charges):
            if c["order_id"] == order_id:
                self.total_charged -= c["amount"]
                self.charges.pop(i)
                return True
        return False
