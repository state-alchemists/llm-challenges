import asyncio
import random
from typing import List, Dict


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[Dict] = []
        self._charged_order_ids: set[str] = set()

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if order_id in self._charged_order_ids:
            # Already charged for this order_id, treat as success for idempotency
            return True
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self._charged_order_ids.add(order_id)
        return True

    async def refund(self, order_id: str, amount: float) -> None:
        await asyncio.sleep(0.01)
        # In a real system, this would interact with a payment processor to issue a refund.
        # For this simulation, we'll just reverse the charge internally.
        for charge in self.charges:
            if charge["order_id"] == order_id and charge["amount"] == amount:
                self.total_charged -= amount
                self.charges.remove(charge)
                self._charged_order_ids.remove(order_id)
                break