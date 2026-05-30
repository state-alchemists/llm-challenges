import asyncio
import random
from typing import Dict, List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._lock = asyncio.Lock()
        self._successful_charges: Dict[str, float] = {}

    async def charge(self, order_id: str, amount: float) -> bool:
        if order_id in self._successful_charges:
            return True

        await asyncio.sleep(0.03)
        if random.random() < self._failure_rate:
            return False

        async with self._lock:
            if order_id in self._successful_charges:
                return True
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            self._successful_charges[order_id] = amount
            return True
