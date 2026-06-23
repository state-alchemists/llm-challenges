import asyncio
import random
from typing import Dict, List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: Dict[str, dict] = {}

    async def charge(self, order_id: str, amount: float) -> bool:
        if order_id in self.charges:
            print(f"Order {order_id}: already charged, skipping duplicate")
            return True
        
        await asyncio.sleep(0.03)
        if random.random() < self._failure_rate:
            return False
        self.total_charged += amount
        self.charges[order_id] = {"order_id": order_id, "amount": amount}
        return True

    async def refund(self, order_id: str) -> None:
        if order_id in self.charges:
            charge = self.charges.pop(order_id)
            self.total_charged -= charge["amount"]
            print(f"Order {order_id}: refunded ${charge['amount']:.2f}")
