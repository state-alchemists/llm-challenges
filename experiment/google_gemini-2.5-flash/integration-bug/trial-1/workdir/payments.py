import asyncio
import random
from typing import List, Dict, Any


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[Dict[str, Any]] = []
        self._charged_orders: set[str] = set()
        self._lock = asyncio.Lock()

    async def charge(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            if order_id in self._charged_orders:
                print(f"PaymentGateway: Order {order_id} already charged.")
                return False

            await asyncio.sleep(0.03)
            if random.random() < self._failure_rate:
                return False

            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            self._charged_orders.add(order_id)
            return True

    async def refund(self, order_id: str, amount: float) -> None:
        async with self._lock:
            # In a real system, you'd find the specific charge and remove it.
            # For this simulation, we'll assume a simple undo of the total_charged.
            if order_id in self._charged_orders:
                self.total_charged -= amount
                # Remove the charge from the list (simple simulation of removal)
                self.charges = [c for c in self.charges if c['order_id'] != order_id]
                self._charged_orders.remove(order_id)
                print(f"PaymentGateway: Refunded order {order_id} for ${amount:.2f}")
            else:
                print(f"PaymentGateway: No charge found for order {order_id} to refund.")
