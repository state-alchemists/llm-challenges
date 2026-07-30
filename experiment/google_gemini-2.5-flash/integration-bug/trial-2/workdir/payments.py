import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._processed_order_ids: set[str] = set()

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if order_id in self._processed_order_ids:
            return False # Already processed this order
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self._processed_order_ids.add(order_id)
        return True

    async def refund(self, order_id: str, amount: float) -> None:
        # Simple refund for the purpose of this exercise. In a real system,
        # this would involve more complex logic to handle partial refunds,
        # multiple items, etc.
        if order_id in self._processed_order_ids:
            self.total_charged -= amount
            self._processed_order_ids.remove(order_id)
            # Remove the charge entry. This assumes one charge per order_id.
            self.charges = [c for c in self.charges if c["order_id"] != order_id]
