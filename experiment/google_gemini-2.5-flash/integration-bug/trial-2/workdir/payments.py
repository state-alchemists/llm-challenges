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
        async with self._lock:
            if order_id in self._charged_order_ids:
                print(f"Order {order_id}: already charged (preventing duplicate)")
                return False
            await asyncio.sleep(0.03)
            if random.random() < self._failure_rate:
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            self._charged_order_ids.add(order_id)
            return True

    async def refund(self, order_id: str, amount: float) -> None:
        async with self._lock:
            if {"order_id": order_id, "amount": amount} in self.charges:
                self.total_charged -= amount
                self.charges.remove({"order_id": order_id, "amount": amount})
                self._charged_order_ids.remove(order_id)
                print(f"Order {order_id}: refunded ${amount:.2f}")
            else:
                print(f"Order {order_id}: refund failed - charge not found")
