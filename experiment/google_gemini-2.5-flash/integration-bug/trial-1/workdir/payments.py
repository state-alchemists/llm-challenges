import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._charged_order_ids: set[str] = set()

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if order_id in self._charged_order_ids:
            # Already charged, prevent duplicate
            return False
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self._charged_order_ids.add(order_id)
        return True

    async def refund(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.02)
        # In a real system, this would interact with a payment processor.
        # For this simulation, we'll just adjust our internal records.
        if order_id in self._charged_order_ids:
            self.total_charged -= amount
            # For simplicity, we'll remove the last charge for this order_id.
            # In a real system, you might want to mark it as refunded or find the specific charge.
            for i in range(len(self.charges) - 1, -1, -1):
                if self.charges[i]["order_id"] == order_id:
                    self.charges.pop(i)
                    break
            self._charged_order_ids.remove(order_id)
            return True
        return False
