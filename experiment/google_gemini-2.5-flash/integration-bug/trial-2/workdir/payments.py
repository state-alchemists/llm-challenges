import asyncio
import random
from typing import List, Set


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._processed_charges: Set[str] = set()

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if order_id in self._processed_charges:
            print(f"Order {order_id}: already processed, preventing duplicate charge")
            return False
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self._processed_charges.add(order_id)
        return True

    async def refund(self, order_id: str, amount: float) -> None:
        await asyncio.sleep(0.01)
        if order_id in self._processed_charges:
            self.total_charged -= amount
            # In a real system, we'd find and remove the specific charge.
            # For this simulation, we'll just remove from processed and adjust total.
            self._processed_charges.remove(order_id)
            print(f"Order {order_id}: refunded ${amount:.2f}")
        else:
            print(f"Order {order_id}: no charge found to refund")
