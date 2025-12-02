from __future__ import annotations

from abc import ABC, abstractmethod

from bot.config import RiskSettings
from bot.models import Position, OrderIntent


class RiskManager(ABC):
    """Enforces exposure limits, daily loss limits, and forced unwind rules."""

    @abstractmethod
    def can_place(self, intent: OrderIntent) -> bool:
        raise NotImplementedError

    @abstractmethod
    def register_fill(self, position: Position) -> None:
        raise NotImplementedError


class SimpleRiskManager(RiskManager):
    def __init__(self, settings: RiskSettings) -> None:
        self.settings = settings

    def can_place(self, intent: OrderIntent) -> bool:
        # Placeholder; will check exposure vs. limits.
        return True

    def register_fill(self, position: Position) -> None:
        # Placeholder; will update internal exposure tracking.
        return None
