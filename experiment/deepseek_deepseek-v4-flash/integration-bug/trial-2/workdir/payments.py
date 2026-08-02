import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        # Orders that have already been charged, for idempotent charging.
        self._charged_order_ids: set = set()
        # Guards the idempotency check + charge so a retried order can never
        # be charged twice concurrently.
        self._lock = asyncio.Lock()

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        return True

    async def charge_once(self, order_id: str, amount: float) -> bool:
        """Charge an order exactly once.

        If the order was already charged successfully, this returns True
        without charging again, so retried checkouts cannot double-charge.
        """
        async with self._lock:
            if order_id in self._charged_order_ids:
                return True
            await asyncio.sleep(0.03)
            if random.random() < self._failure_rate:
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            self._charged_order_ids.add(order_id)
            return True
