import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._lock = asyncio.Lock()

    async def charge(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            await asyncio.sleep(0.03)
            if random.random() < self._failure_rate:
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            return True

    async def refund(self, order_id: str, amount: float) -> None:
        async with self._lock:
            await asyncio.sleep(0.01)
            # Find and remove the charge. Assuming one charge per order_id for simplicity.
            # In a real system, charges might have unique transaction IDs.
            for i, charge in enumerate(self.charges):
                if charge["order_id"] == order_id and charge["amount"] == amount:
                    self.total_charged -= amount
                    self.charges.pop(i)
                    print(f"Refunded order {order_id} for ${amount:.2f}")
                    return
            print(f"Warning: Could not find charge for order {order_id} to refund.")
