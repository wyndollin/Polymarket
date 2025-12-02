from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from bot.models import FillEvent, Position


class FillHandler(ABC):
    """Handles partial/full fills and triggers exit logic and PnL updates."""

    @abstractmethod
    def on_fills(self, fills: List[FillEvent]) -> None:
        raise NotImplementedError


class SimpleFillHandler(FillHandler):
    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}

    def on_fills(self, fills: List[FillEvent]) -> None:
        # Placeholder; will update positions and trigger exits.
        return None
