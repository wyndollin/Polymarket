from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from bot.models import LiveOrder, FillEvent, OrderBookSnapshot, Position


class Persistence(ABC):
    """Abstract persistence layer for orders, fills, snapshots, and PnL."""

    @abstractmethod
    def save_orders(self, orders: Iterable[LiveOrder]) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_fills(self, fills: Iterable[FillEvent]) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_position(self, position: Position) -> None:
        raise NotImplementedError


class InMemoryPersistence(Persistence):
    def __init__(self) -> None:
        self.orders: list[LiveOrder] = []
        self.fills: list[FillEvent] = []
        self.snapshots: list[OrderBookSnapshot] = []
        self.positions: list[Position] = []

    def save_orders(self, orders: Iterable[LiveOrder]) -> None:
        self.orders.extend(list(orders))

    def save_fills(self, fills: Iterable[FillEvent]) -> None:
        self.fills.extend(list(fills))

    def save_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        self.snapshots.append(snapshot)

    def save_position(self, position: Position) -> None:
        self.positions.append(position)
