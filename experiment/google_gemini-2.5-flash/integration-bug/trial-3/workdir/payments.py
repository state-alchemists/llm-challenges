import asyncio
import random
from typing import List, Set


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._processed_charges: Set[str] = set()
        self._lock = asyncio.Lock()

    async def charge(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            if order_id in self._processed_charges:
                print(f"PaymentGateway: Skipping duplicate charge for order {order_id}")
                return False
            await asyncio.sleep(0.03)
            if random.random() < self._failure_rate:
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            self._processed_charges.add(order_id)
            return True

    async def refund(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            if order_id not in self._processed_charges:
                print(f"PaymentGateway: No charge found for order {order_id} to refund")
                return False
            
            # This is a simplified refund. In a real system, you'd match the exact charge.
            # For this simulation, we assume a direct reversal is sufficient.
            if self.total_charged >= amount:
                self.total_charged -= amount
                # Remove from charges list for accurate accounting in this simulation
                self.charges = [c for c in self.charges if c["order_id"] != order_id]
                self._processed_charges.remove(order_id)
                print(f"PaymentGateway: Refunded {amount} for order {order_id}")
                return True
            else:
                print(f"PaymentGateway: Insufficient total charged to refund {amount} for order {order_id}")
                return False
