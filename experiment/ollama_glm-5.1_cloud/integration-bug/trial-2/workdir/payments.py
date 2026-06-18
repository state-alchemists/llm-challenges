import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._charge_lock = asyncio.Lock()

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        return True

    async def try_charge(self, order_id: str, amount: float) -> bool:
        """Idempotent charge: at most one successful charge per order_id.

        Returns True if the charge succeeded (or already succeeded previously),
        False if the charge was declined.
        """
        async with self._charge_lock:
            for c in self.charges:
                if c["order_id"] == order_id:
                    return True
            if random.random() < self._failure_rate:
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            return True