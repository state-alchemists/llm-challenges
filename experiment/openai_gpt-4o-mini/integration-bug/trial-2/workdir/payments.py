import asyncio
import random
from typing import List

class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self.processed_orders: set = set()  # Initialize the set here
        self._lock = asyncio.Lock()  # Initialize the lock here

    async def charge(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            # Avoid double charging
            if order_id in self.processed_orders:
                print(f"Debug: Payment of {amount} has already been processed for {order_id}.")
                return False
            # Simulate payment processing time
            await asyncio.sleep(0.03)
            if random.random() < self._failure_rate:
                print(f"Debug: Payment failed for {order_id}.")
                return False
            self.total_charged += amount
            print(f"Debug: Total charged updated to {self.total_charged} for {order_id}.")
            self.charges.append({"order_id": order_id, "amount": amount})
            self.processed_orders.add(order_id)  # Mark order as processed
            print(f"Debug: Payment of {amount} processed for {order_id}.")
            return True

    async def refund(self, order_id: str, amount: float) -> bool:
        async with self._lock:
            if order_id not in self.processed_orders:
                print(f"Debug: Refund for {order_id} not applicable, order was not processed.")
                return False
            self.total_charged -= amount
            self.processed_orders.remove(order_id)  # Remove order from processed list
            print(f"Debug: Refunding {amount} for {order_id}.")
            return True