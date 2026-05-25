import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._refunded_charges: List[dict] = []

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        return True

    async def refund(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.01)
        # In a real system, we'd interact with a payment provider to actually
        # process the refund. For this simulation, we'll just adjust our internal
        # accounting and record the refund.
        if {"order_id": order_id, "amount": amount} in self.charges:
            self.total_charged -= amount
            self.charges.remove({"order_id": order_id, "amount": amount})
            self._refunded_charges.append({"order_id": order_id, "amount": amount})
            return True
        return False
