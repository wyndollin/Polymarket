from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List

from bot.config import Settings, RiskSettings, FeeModel
from bot.models import MarketMetadata, OrderBookSnapshot, OrderIntent


class StrategyEngine(ABC):
    """Decides whether to place orders, and if so, side/price/size/TTL.

    Inputs:
    - Orderbook snapshot
    - Market metadata
    - Risk settings
    - Fee model
    - Latency stats (to be added later)
    """

    @abstractmethod
    def generate_order_intents(
        self,
        market: MarketMetadata,
        book: OrderBookSnapshot,
    ) -> List[OrderIntent]:
        raise NotImplementedError


class SimpleSpreadStrategy(StrategyEngine):
    """Very basic placeholder strategy.

    For now, this only illustrates the interface and does not place real orders.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.risk: RiskSettings = settings.risk
        self.fees: FeeModel = settings.fee_model

    def generate_order_intents(
        self,
        market: MarketMetadata,
        book: OrderBookSnapshot,
    ) -> List[OrderIntent]:
        return []
