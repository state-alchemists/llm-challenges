import asyncio
import random
from typing import List

class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if random.random() < self._failure_rate:
            print(f"Order {order_id}: payment failed due to failure rate.")
            return False
        if any(charge["order_id"] == order_id for charge in self.charges):
            print(f"Order {order_id} already charged.")
            return False  # Prevent duplicate charges
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        print(f"Order {order_id}: charged ${amount} successfully.")
        return True