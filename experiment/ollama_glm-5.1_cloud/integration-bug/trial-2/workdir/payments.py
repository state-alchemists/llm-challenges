import asyncio
import random
from typing import Dict, List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._results: Dict[str, bool] = {}

    async def charge(self, order_id: str, amount: float) -> bool:
        # Idempotency: return the previous result for the same order_id
        if order_id in self._results:
            return self._results[order_id]
        await asyncio.sleep(0.03)
        if random.random() < self._failure_rate:
            self._results[order_id] = False
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self._results[order_id] = True
        return True
