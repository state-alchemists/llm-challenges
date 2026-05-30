import asyncio
import random
from typing import List, Set


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._processed_charges: Set[str] = set() # For idempotency

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)

        if order_id in self._processed_charges:
            print(f"PaymentGateway: {order_id} already processed, skipping duplicate charge.")
            return True # Idempotent: already charged successfully

        if random.random() < self._failure_rate:
            return False
        
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self._processed_charges.add(order_id)
        return True

    async def refund(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.02) # Simulate async operation
        for i, charge in enumerate(self.charges):
            if charge["order_id"] == order_id:
                self.total_charged -= amount
                self.charges.pop(i)
                self._processed_charges.discard(order_id)
                return True
        return False
