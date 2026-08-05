import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._successful_charges: set[str] = set() # To track successful charges and ensure idempotency

    async def charge(self, order_id: str, amount: float) -> bool:
        if order_id in self._successful_charges:
            print(f"Order {order_id}: already successfully charged. Skipping.")
            return True # Idempotency: already charged

        await asyncio.sleep(0.03)
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self._successful_charges.add(order_id) # Mark as successfully charged
        return True

    async def refund(self, order_id: str, amount: float) -> None:
        await asyncio.sleep(0.01) # Simulate async I/O
        print(f"Order {order_id}: REFUNDED ${amount:.2f}")
        # In a real system, you'd integrate with a payment provider to process the refund.
        # For this simulation, we'll just adjust our internal totals and records.
        self.total_charged -= amount
        # Remove the charge from the list, assuming one charge per order_id for simplicity.
        self.charges = [c for c in self.charges if c["order_id"] != order_id]
        self._successful_charges.discard(order_id)
