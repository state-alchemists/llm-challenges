import asyncio
import random
from typing import List

class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []

    async def charge(self, order_id: str, amount: float) -> bool:
        # Check if the order has already been charged
        if self.has_order(order_id):
            print(f"Payment for order {order_id} has already been charged.")  # Debugging statement
            return False

        await asyncio.sleep(0.03)  # Simulate variability in processing
        # Fail based on the specified failure rate
        if random.random() < self._failure_rate:
            print(f"Payment for order {order_id} failed due to failure rate.")  # Debugging statement
            return False
        self.total_charged += amount
        self.charges.append({"order_id": order_id, "amount": amount})
        print(f"Processed payment for order {order_id}: ${amount:.2f}.")  # Debugging statement
        return True
    
    def has_order(self, order_id: str) -> bool:
        return any(charge['order_id'] == order_id for charge in self.charges)
    
    def refund(self, order_id: str, amount: float) -> None:
        # Process refund logic
        if self.has_order(order_id):
            self.total_charged -= amount
            self.charges = [charge for charge in self.charges if charge['order_id'] != order_id]
            print(f"Refund processed for order {order_id}: ${amount:.2f}.")