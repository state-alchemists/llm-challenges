import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._lock = asyncio.Lock()  # Add a lock for thread-safety

    async def charge(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            await asyncio.sleep(0.03)
            if random.random() < self._failure_rate:
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            return True

    async def refund(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            # For simplicity, assuming a successful refund means finding the charge
            # and reversing it. In a real system, this would involve external API calls
            # and more robust matching/tracking.
            for i, charge in enumerate(self.charges):
                # Match by order_id and amount to ensure we refund the correct charge
                if charge["order_id"] == order_id and charge["amount"] == amount:
                    self.total_charged -= amount
                    self.charges.pop(i)
                    return True
            return False  # Charge not found or amount mismatch
