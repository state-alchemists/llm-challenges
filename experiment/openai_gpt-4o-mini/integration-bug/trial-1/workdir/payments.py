import asyncio
import random
from typing import List, Set

class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self.processed_orders: Set[str] = set()  # Track processed orders

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if order_id in self.processed_orders:  # Avoid double charges
            return False
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        print(f"Charging {order_id} a total of {amount}")
        self.charges.append({"order_id": order_id, "amount": amount})
        self.processed_orders.add(order_id)  # Mark order as processed
        return True