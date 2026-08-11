import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._charged_orders = set()

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if order_id in self._charged_orders:
            # Already charged this order, consider it a success for idempotency
            return True

        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self._charged_orders.add(order_id)
        return True

    async def refund(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.01) # Simulate refund processing time
        if order_id in self._charged_orders:
            self.total_charged -= amount
            # Remove the charge from the list (simple approach, might need more robust handling for real systems)
            self.charges = [charge for charge in self.charges if charge["order_id"] != order_id]
            self._charged_orders.remove(order_id)
            return True
        return False
