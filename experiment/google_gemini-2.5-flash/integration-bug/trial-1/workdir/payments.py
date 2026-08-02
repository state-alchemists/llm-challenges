import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._processed_orders: set = set()

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if order_id in self._processed_orders:
            print(f"Order {order_id}: already processed, skipping charge")
            return True  # Idempotent: already charged, consider it successful

        if random.random() < self._failure_rate:
            return False

        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self._processed_orders.add(order_id)
        return True

    async def refund(self, order_id: str, amount: float) -> None:
        await asyncio.sleep(0.01)
        # For simplicity, we'll just decrement total_charged and remove from processed_orders
        # In a real system, this would involve a more complex refund process.
        self.total_charged -= amount
        # Remove the order from processed_orders to allow a retry if needed, or handle as a refund record
        if order_id in self._processed_orders:
            self._processed_orders.remove(order_id)
        # For charges list, finding and removing a specific charge might be complex in a mock scenario
        # Given the requirements, just adjusting total_charged and _processed_orders is sufficient for this mock.
        print(f"Order {order_id}: refunded {amount}")
