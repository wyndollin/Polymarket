from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List

import requests

from bot.config import Settings
from bot.models import MarketMetadata


class MarketScanner(ABC):
    """Continuously fetches candidate markets and market metadata from Gamma API.

    Responsibilities:
    - Poll `GET /markets` and optionally `GET /events`.
    - Filter by expiry, tags, and activity.
    - Emit a list/stream of `MarketMetadata` instances.
    """

    @abstractmethod
    def scan(self) -> Iterable[MarketMetadata]:  # could be generator or async stream later
        raise NotImplementedError


class GammaMarketScanner(MarketScanner):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def scan(self) -> Iterable[MarketMetadata]:
        # Placeholder: just a stub to be implemented.
        # Real implementation will page through `GET /markets` and map to `MarketMetadata`.
        return []
