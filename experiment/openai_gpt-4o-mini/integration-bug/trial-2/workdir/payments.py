import asyncio
import random
from typing import List, Dict

class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self.lock = asyncio.Lock()  # Adding lock for synchronization
        self.charge_status: Dict[str, bool] = {}  # Track charge statuses

    async def charge(self, order_id: str, amount: float) -> bool:
        async with self.lock:  # Ensure only one charge process at a time
            print(f"Attempting to charge order {order_id}.")
            await asyncio.sleep(0.03)
            if order_id in self.charge_status:
                print(f"Charge for {order_id} already processed.")
                return False
            if random.random() < self._failure_rate:
                print(f"Charge for {order_id} failed due to random failure.")
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            self.charge_status[order_id] = True  # Mark as charged
            print(f"Charge for {order_id} approved.")
            return True

    async def has_charged(self, order_id: str) -> bool:
        async with self.lock:  # Locking during the check
            return self.charge_status.get(order_id, False)  # Check charged states