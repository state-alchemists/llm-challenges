import asyncio
import random
from typing import List, Set


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._processed_orders: Set[str] = set()  # To track successfully processed orders

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)  # Simulate async operation

        if order_id in self._processed_orders:
            print(f"Order {order_id}: already processed, returning success")
            return True  # Idempotency: already charged, report success

        if random.random() < self._failure_rate:
            return False
        
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self._processed_orders.add(order_id)
        return True
