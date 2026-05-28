import asyncio
import random
from typing import List, Optional


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._lock = asyncio.Lock()

    async def charge(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            # Prevent duplicate charges for the same order_id
            if any(c["order_id"] == order_id for c in self.charges):
                print(f"PaymentGateway: Attempted duplicate charge for {order_id}")
                return False

            await asyncio.sleep(0.03)
            if random.random() < self._failure_rate:
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            return True

    async def refund(self, order_id: str) -> bool:
        async with self._lock:
            charge_index: Optional[int] = None
            for i, charge in enumerate(self.charges):
                if charge["order_id"] == order_id:
                    charge_index = i
                    break

            if charge_index is None:
                print(f"PaymentGateway: No charge found for order {order_id} to refund")
                return False

            charge = self.charges.pop(charge_index)
            self.total_charged -= charge["amount"]
            print(f"PaymentGateway: Refunded {order_id} for ${charge['amount']:.2f}")
            return True
