import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []

    async def charge(self, order_id: str, amount: float) -> bool:
        print(f"Attempting to charge {order_id} for {amount}")
        await asyncio.sleep(0.03)
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        return True  # Ensure to return True upon success

    async def refund(self, order_id: str, amount: float) -> None:
        await asyncio.sleep(0.01)  # simulate refund processing
        self.total_charged -= amount
        self.charges = [charge for charge in self.charges if charge['order_id'] != order_id]