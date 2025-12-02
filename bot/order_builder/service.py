from __future__ import annotations

from abc import ABC, abstractmethod

from bot.config import Settings
from bot.models import OrderIntent


class OrderBuilder(ABC):
    """Builds and signs CLOB order payloads from `OrderIntent` objects."""

    @abstractmethod
    def build(self, intent: OrderIntent) -> dict:
        """Return a payload ready for submission to the CLOB REST API."""
        raise NotImplementedError


class ClobOrderBuilder(OrderBuilder):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build(self, intent: OrderIntent) -> dict:
        # Placeholder; real implementation will use py-clob-client and attach L2 headers.
        return {
            "market_id": intent.market_id,
            "side": intent.side.value,
            "price": intent.price,
            "size": intent.size,
            "ttl": intent.ttl_seconds,
            "client_order_id": intent.client_order_id,
            "metadata": intent.metadata,
        }
