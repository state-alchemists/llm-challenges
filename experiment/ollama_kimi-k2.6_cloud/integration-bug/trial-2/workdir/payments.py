import asyncio
import random
from typing import List, Dict


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._processed: Dict[str, bool] = {}
        self._lock = asyncio.Lock()

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        async with self._lock:
            if order_id in self._processed:
                return self._processed[order_id]
            if random.random() < self._failure_rate:
                self._processed[order_id] = False
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            self._processed[order_id] = True
            return True
