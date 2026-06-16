"""Tests for inventory.Inventory."""

from __future__ import annotations

import pytest
from inventory import Inventory, OutOfStock


def test_two_inventories_do_not_share_state() -> None:
    a = Inventory()
    b = Inventory()
    a.add("apple", 5)
    assert b.available("apple") == 0, "Inventories must not share storage"


def test_add_accumulates() -> None:
    inv = Inventory()
    inv.add("apple", 3)
    inv.add("apple", 4)
    assert inv.available("apple") == 7


def test_reserve_up_to_available() -> None:
    inv = Inventory({"apple": 5})
    inv.reserve("apple", 5)
    assert inv.available("apple") == 0


def test_reserve_more_than_available_raises() -> None:
    inv = Inventory({"apple": 5})
    with pytest.raises(OutOfStock):
        inv.reserve("apple", 6)


def test_release_cannot_go_negative() -> None:
    inv = Inventory({"apple": 5})
    inv.reserve("apple", 2)
    with pytest.raises(ValueError):
        inv.release("apple", 5)
