from __future__ import annotations

from abc import ABC, abstractmethod


class Backtester(ABC):
    """Replays historical data from the Data-API to evaluate strategy parameters."""

    @abstractmethod
    def run(self) -> None:
        raise NotImplementedError


class SimpleBacktester(Backtester):
    def run(self) -> None:
        # Placeholder; will pull `GET /trades` and apply strategy offline.
        return None
