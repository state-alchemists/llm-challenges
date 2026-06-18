import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._successful_charges: set[str] = set()

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if order_id in self._successful_charges:
            return False  # Already charged, prevent duplicate

        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self._successful_charges.add(order_id)
        return True

    async def refund(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.01)  # Simulate network latency
        charge_found = False
        for i, charge in enumerate(self.charges):
            if charge["order_id"] == order_id and charge["amount"] == amount:
                del self.charges[i]
                self.total_charged -= amount
                charge_found = True
                break
        if charge_found:
            self._successful_charges.discard(order_id)
        return charge_found

