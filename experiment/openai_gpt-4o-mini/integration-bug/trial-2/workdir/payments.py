import asyncio
import random
from typing import List

class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []

    async def charge(self, order_id: str, amount: float) -> bool:
        # Check for existing charges
        if self.is_order_charged(order_id):
            print(f"Order {order_id}: Already charged, skipping.")
            return False  # Prevent further charging for the same order

        # Simulate the charge process
        await asyncio.sleep(0.03)  # Simulate network delay
        if random.random() < self._failure_rate:
            return False  # Charge failed
        
        # Charge was successful
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        return True

    async def refund(self, order_id: str) -> bool:
        await asyncio.sleep(0.03)  # Simulate processing delay
        charge = next((charge for charge in self.charges if charge["order_id"] == order_id), None)

        if charge:
            self.total_charged -= charge["amount"]
            self.charges.remove(charge)
            print(f"Order {order_id}: Refunded.")
            return True  # Successful refund

        return False  # No charge found to refund

    def is_order_charged(self, order_id: str) -> bool:
        return any(charge for charge in self.charges if charge["order_id"] == order_id)