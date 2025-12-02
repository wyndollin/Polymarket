from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

import requests

from bot.config import Settings
from bot.models import LiveOrder


class ExecutionEngine(ABC):
    """Submits orders to the CLOB, manages cancellations, and queries status."""

    @abstractmethod
    def submit_orders(self, payloads: List[dict]) -> List[LiveOrder]:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_hash: str) -> None:
        raise NotImplementedError


class RestExecutionEngine(ExecutionEngine):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def submit_orders(self, payloads: List[dict]) -> List[LiveOrder]:
        # Placeholder; will call POST /order or batch POST /orders.
        return []

    def cancel_order(self, order_hash: str) -> None:
        # Placeholder; will call DELETE /order/{id}.
        return None
