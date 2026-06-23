import asyncio
from payments import PaymentGateway

class Inventory:
    def __init__(self, stock: int):
        self._stock = stock

    async def check_stock(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        return self._stock >= quantity

    async def decrement_and_charge(self, quantity: int, order_id: str, gateway: PaymentGateway, price: float) -> bool:
        if not await self.check_stock(quantity):
            return False  # Cannot fulfill order

        if self._stock < quantity:
            return False  # Cannot fulfill order

        self._stock -= quantity  # Decrement stock after charge is confirmed
        charged = await gateway.charge(order_id, quantity * price)
        if not charged:
            return False  # Payment failed

        self._stock -= quantity
        if not charged:
            return False  # Payment failed
        if not charged:
            self._stock += quantity  # Rollback stock on charge failure
            return False  # Charge failed

        return True

    async def decrement(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        if self._stock >= quantity:
            self._stock -= quantity
            return True
        return False

    async def increment(self, quantity: int) -> None:
        await asyncio.sleep(0.01)
        self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock