import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._charged_orders = set()

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        
        # Prevent duplicate charges
        if order_id in self._charged_orders:
            return False
            
        if random.random() < self._failure_rate:
            return False
        
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        self._charged_orders.add(order_id)
        return True
    
    async def refund(self, order_id: str, amount: float) -> None:
        # Not strictly needed by the new checkout flow, but good for completeness
        await asyncio.sleep(0.01)
        self.total_charged -= amount
        # In a real system, we'd remove from self.charges or add a refund record
        if order_id in self._charged_orders:
            self._charged_orders.remove(order_id)
