from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone

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

    @abstractmethod
    def subscribe_market(self, market_id: str) -> None:
        """Start tracking a market."""
        raise NotImplementedError

    @abstractmethod
    def get_cheap_side_price(self, market_id: str) -> Optional[float]:
        """Return current cheap side price (lower of YES/NO)."""
        raise NotImplementedError

    @abstractmethod
    def check_threshold_crossing(self, market_id: str, threshold: float) -> bool:
        """Check if cheap side has crossed the threshold."""
        raise NotImplementedError


class InMemoryOrderbookEngine(OrderbookEngine):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._books: Dict[str, OrderBookSnapshot] = {}
        self._subscribed_markets: set[str] = set()

    def get_snapshot(self, market_id: str) -> OrderBookSnapshot | None:
        return self._books.get(market_id)

    def subscribe_market(self, market_id: str) -> None:
        """Start tracking a market."""
        self._subscribed_markets.add(market_id)
        # In a real implementation, this would subscribe to WebSocket feed
        # For now, we'll rely on manual updates via update_snapshot

    def update_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        """Update orderbook snapshot for a market."""
        self._books[snapshot.market_id] = snapshot

    def get_cheap_side_price(self, market_id: str) -> Optional[float]:
        """Return current cheap side price (lower of YES/NO prices)."""
        snapshot = self.get_snapshot(market_id)
        if not snapshot:
            return None
        
        # For YES/NO markets, we need to get prices for both outcomes
        # This is a simplified version - in reality, you'd need to query
        # both YES and NO market orderbooks
        # For now, assume best_ask represents the buy price
        if snapshot.best_ask is not None:
            return snapshot.best_ask
        
        # Fallback to last trade price
        if snapshot.last_trade_price is not None:
            return snapshot.last_trade_price
        
        return None

    def check_threshold_crossing(self, market_id: str, threshold: float) -> bool:
        """Check if cheap side has crossed the threshold (price <= threshold)."""
        cheap_price = self.get_cheap_side_price(market_id)
        if cheap_price is None:
            return False
        return cheap_price <= threshold

    def get_yes_no_prices(self, market_id: str) -> Optional[Tuple[float, float]]:
        """Get both YES and NO prices for a market.
        
        Returns (yes_price, no_price) or None if unavailable.
        In practice, you'd need to query separate orderbooks for YES and NO outcomes.
        """
        snapshot = self.get_snapshot(market_id)
        if not snapshot:
            return None
        
        # Simplified: assume we can derive from snapshot
        # Real implementation would query both outcome markets
        if snapshot.best_ask is not None:
            yes_price = snapshot.best_ask
            no_price = 1.0 - yes_price  # Assuming they sum to 1.0
            return (yes_price, no_price)
        
        return None
