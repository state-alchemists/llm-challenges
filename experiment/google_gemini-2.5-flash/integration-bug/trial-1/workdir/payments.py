import asyncio
import random
from typing import List, Set


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._successful_charges: Set[str] = set()
        self._lock = asyncio.Lock()

    async def charge(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            if order_id in self._successful_charges:
                # Idempotency: already charged, so return True
                return True
            await asyncio.sleep(0.03)
            if random.random() < self._failure_rate:
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            self._successful_charges.add(order_id)
            return True

    async def refund(self, order_id: str, amount: float) -> None:
        async with self._lock:
            await asyncio.sleep(0.01)
            if order_id in self._successful_charges:
                self.total_charged -= amount
                # Remove the charge from the list as well (simple implementation, could be more robust)
                self.charges = [c for c in self.charges if c["order_id"] != order_id]
                self._successful_charges.remove(order_id)
