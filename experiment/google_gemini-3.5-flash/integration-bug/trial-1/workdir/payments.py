import asyncio
import random
from typing import List, Set


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._lock = asyncio.Lock()
        self._processing_orders: Set[str] = set()
        self._charged_orders: Set[str] = set()

    async def charge(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            # Prevent concurrent duplicate charges for the same order_id
            if order_id in self._processing_orders or order_id in self._charged_orders:
                return False
            self._processing_orders.add(order_id)

        try:
            await asyncio.sleep(0.03)
            success = random.random() >= self._failure_rate
        except Exception as e:
            async with self._lock:
                self._processing_orders.discard(order_id)
            raise e

        async with self._lock:
            self._processing_orders.discard(order_id)
            if success:
                self.total_charged += amount
                self.charges.append({"order_id": order_id, "amount": amount})
                self._charged_orders.add(order_id)
                return True
            return False
