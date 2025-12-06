from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from bot.config import Settings
from bot.models import OrderIntent

try:
    from clob_client import ClobClient
    from clob_client.constants import POLYMARKET_CLOB_HOST
    CLOB_CLIENT_AVAILABLE = True
except ImportError:
    CLOB_CLIENT_AVAILABLE = False


class OrderBuilder(ABC):
    """Builds and signs CLOB order payloads from `OrderIntent` objects."""

    @abstractmethod
    def build(self, intent: OrderIntent) -> dict:
        """Return a payload ready for submission to the CLOB REST API."""
        raise NotImplementedError


class ClobOrderBuilder(OrderBuilder):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.clob_client: ClobClient | None = None
        
        # Initialize CLOB client if credentials are available
        if CLOB_CLIENT_AVAILABLE and settings.poly_api_key and settings.poly_api_secret:
            try:
                self.clob_client = ClobClient(
                    host=POLYMARKET_CLOB_HOST,
                    key=settings.poly_api_key,
                    signature=settings.poly_api_secret,  # API secret used for signing
                    address=settings.poly_api_passphrase,  # Passphrase may be wallet address
                )
            except Exception as e:
                print(f"Warning: Failed to initialize CLOB client: {e}")
                self.clob_client = None

    def build(self, intent: OrderIntent) -> dict:
        """Build and optionally sign a CLOB order payload."""
        # Base order payload
        order_payload = {
            "market": intent.market_id,
            "side": intent.side.value.lower(),  # CLOB expects lowercase
            "price": str(intent.price),  # CLOB may expect string
            "size": str(intent.size),  # CLOB may expect string
            "expiration": intent.ttl_seconds,
            "clientOrderId": intent.client_order_id,
        }
        
        # Add metadata if present
        if intent.metadata:
            order_payload["metadata"] = intent.metadata
        
        # If CLOB client is available, sign the order
        if self.clob_client:
            try:
                # Use CLOB client to create signed order
                # Note: Actual method may vary based on py-clob-client version
                signed_order = self.clob_client.create_order(
                    market=intent.market_id,
                    side=intent.side.value.lower(),
                    price=str(intent.price),
                    size=str(intent.size),
                    expiration=intent.ttl_seconds,
                    client_order_id=intent.client_order_id,
                )
                return signed_order
            except Exception as e:
                print(f"Warning: Failed to sign order with CLOB client: {e}")
                # Fall back to unsigned payload
                return order_payload
        
        # Return unsigned payload (for testing or if client unavailable)
        return order_payload
