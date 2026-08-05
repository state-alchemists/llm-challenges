import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._charged_order_ids = set()
        self._lock = asyncio.Lock()

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        return True

    async def charge_once(self, order_id: str, amount: float) -> bool:
        """Charge an order at most once per gateway instance.

        The lock makes the check-then-charge atomic, so two concurrent
        submissions of the same order_id cannot both be charged.
        """
        async with self._lock:
            if order_id in self._charged_order_ids:
                return False
            charged = await self.charge(order_id, amount)
            if charged:
                self._charged_order_ids.add(order_id)
            return charged
