import asyncio
import random
from typing import List, Set


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._successful_charges: Set[str] = set() # To track successfully charged order_ids for idempotency

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)

        if order_id in self._successful_charges:
            print(f"Order {order_id}: already successfully charged (idempotent)")
            return True # Already charged, so consider it a success

        if random.random() < self._failure_rate:
            print(f"Order {order_id}: payment randomly failed")
            return False

        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self._successful_charges.add(order_id)
        print(f"Order {order_id}: charged {amount:.2f}")
        return True

    async def refund(self, order_id: str, amount: float) -> None:
        await asyncio.sleep(0.02) # Simulate async work
        # In a real system, you'd integrate with a payment processor's refund API
        # For this mock, we'll reverse the charge locally
        if order_id in self._successful_charges:
            self.total_charged -= amount
            # Remove the charge from the list. In a real system, you'd mark it as refunded.
            self.charges = [c for c in self.charges if c["order_id"] != order_id]
            self._successful_charges.discard(order_id)
            print(f"Order {order_id}: refunded {amount:.2f}")
        else:
            print(f"Order {order_id}: no successful charge found to refund")
