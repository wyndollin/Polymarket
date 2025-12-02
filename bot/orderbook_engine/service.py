from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from bot.config import Settings
from bot.models import OrderBookSnapshot


class OrderbookEngine(ABC):
    """Maintains near-real-time in-memory orderbooks for candidate markets.

    Sources:
    - CLOB WebSocket (orderbook deltas, trades)
    - CLOB REST snapshots as fallback

    Provides:
    - Current best bid/ask
    - Aggregated depth
    - Spread and liquidity filters
    """

    @abstractmethod
    def get_snapshot(self, market_id: str) -> OrderBookSnapshot | None:
        raise NotImplementedError


class InMemoryOrderbookEngine(OrderbookEngine):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._books: Dict[str, OrderBookSnapshot] = {}

    def get_snapshot(self, market_id: str) -> OrderBookSnapshot | None:
        return self._books.get(market_id)
