"""Interface definition for this component.

This is intentionally minimal and focused on the responsibilities described in the
high-level design. Concrete implementations will live alongside this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List

from bot.models import MarketMetadata, OrderBookSnapshot, OrderIntent, LiveOrder, FillEvent, Position
from bot.config import Settings, RiskSettings, FeeModel


class Component(ABC):
    """Base marker interface for lifecycle hooks if needed later."""

    def start(self) -> None:
        """Start the component (e.g., spawn tasks / threads)."""

    def stop(self) -> None:
        """Stop the component and clean up resources."""

