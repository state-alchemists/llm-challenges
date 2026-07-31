import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._charged_orders: set[str] = set()
        self._lock = asyncio.Lock()

    async def charge(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            if order_id in self._charged_orders:
                print(f"Order {order_id}: already charged, skipping duplicate.")
                return True # Idempotency: already charged, so treat as success.

            await asyncio.sleep(0.03)
            if random.random() < self._failure_rate:
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            self._charged_orders.add(order_id)
            return True

    async def refund(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            if order_id not in self._charged_orders:
                print(f"Order {order_id}: no charge to refund.")
                return False

            # This simple refund assumes the exact amount is always refunded.
            # In a real system, you'd match by charge ID or be more sophisticated.
            charge_found = False
            for i, charge in enumerate(self.charges):
                if charge["order_id"] == order_id and charge["amount"] == amount:
                    self.total_charged -= amount
                    self.charges.pop(i)
                    self._charged_orders.remove(order_id)
                    charge_found = True
                    break
            
            if not charge_found:
                print(f"Order {order_id}: charge not found for refund (amount mismatch or already refunded).")
                return False

            print(f"Order {order_id}: refunded ${amount:.2f}")
            return True
