import asyncio
import random
from typing import List, Set


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._lock = asyncio.Lock()
        self._processed_charges: Set[str] = set() # To track successfully processed charges
        self._refunded_charges: Set[str] = set()  # To track refunded charges

    async def charge(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            if order_id in self._processed_charges or order_id in self._refunded_charges:
                return False  # Already processed or refunded

            await asyncio.sleep(0.03)
            if random.random() < self._failure_rate:
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            self._processed_charges.add(order_id)
            return True

    async def refund(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            if order_id not in self._processed_charges or order_id in self._refunded_charges:
                return False # Not charged or already refunded
            
            await asyncio.sleep(0.02) # Simulate refund processing
            self.total_charged -= amount
            # We don't remove from self.charges to keep a record of all transactions, but mark as refunded
            for charge in self.charges:
                if charge["order_id"] == order_id:
                    charge["status"] = "refunded"
            self._processed_charges.remove(order_id)
            self._refunded_charges.add(order_id)
            return True
