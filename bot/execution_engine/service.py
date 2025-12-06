from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime, timezone
import time
import random

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ExecutionEngine(ABC):
    """Submits orders to the CLOB, manages cancellations, and queries status."""

    @abstractmethod
    def submit_order(self, payload: dict) -> LiveOrder:
        """Submit a single order."""
        raise NotImplementedError

    @abstractmethod
    def submit_orders(self, payloads: List[dict]) -> List[LiveOrder]:
        """Submit multiple orders."""
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_hash: str) -> None:
        """Cancel an order."""
        raise NotImplementedError

    @abstractmethod
    def wait_for_fills(
        self,
        orders: List[LiveOrder],
        timeout_seconds: int = 60,
    ) -> List[FillEvent]:
        """Monitor orders until filled or timeout."""
        raise NotImplementedError


class RestExecutionEngine(ExecutionEngine):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.clob_base_url
        self._pending_orders: dict[str, LiveOrder] = {}
        
        # Setup session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "DELETE"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _get_headers(self) -> dict:
        """Get headers for authenticated requests."""
        headers = {
            "Content-Type": "application/json",
        }
        # Add authentication headers if available
        if self.settings.poly_api_key:
            headers["Authorization"] = f"Bearer {self.settings.poly_api_key}"
        return headers

    def submit_order(self, payload: dict) -> LiveOrder:
        """Submit a single order to CLOB with retry logic."""
        url = f"{self.base_url}/order"
        max_retries = 3
        order_data = None
        
        for attempt in range(max_retries):
            try:
                response = self.session.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=10,
                )
                response.raise_for_status()
                order_data = response.json()
                break
            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    # Last attempt failed
                    print(f"Error submitting order after {max_retries} attempts: {e}")
                    # Return failed order
                    intent = OrderIntent(
                        market_id=payload.get("market", ""),
                        side=payload.get("side", "").upper(),
                        price=float(payload.get("price", 0)),
                        size=float(payload.get("size", 0)),
                        ttl_seconds=payload.get("expiration", 120),
                        client_order_id=payload.get("clientOrderId", ""),
                        metadata=payload.get("metadata", {}),
                    )
                    return LiveOrder(
                        order_hash="",
                        intent=intent,
                        created_at=datetime.now(timezone.utc),
                        status="failed",
                    )
                # Exponential backoff
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait_time)
        
        if order_data is None:
            # Should not reach here, but handle just in case
            raise RuntimeError("Failed to submit order")
        
        # Create LiveOrder from response
        # Note: Actual response structure may vary
        order_hash = order_data.get("hash") or order_data.get("id", "")
        status = order_data.get("status", "pending")
        
        # Reconstruct OrderIntent from payload
        intent = OrderIntent(
            market_id=payload.get("market", ""),
            side=payload.get("side", "").upper(),
            price=float(payload.get("price", 0)),
            size=float(payload.get("size", 0)),
            ttl_seconds=payload.get("expiration", 120),
            client_order_id=payload.get("clientOrderId", ""),
            metadata=payload.get("metadata", {}),
        )
        
        live_order = LiveOrder(
            order_hash=order_hash,
            intent=intent,
            created_at=datetime.now(timezone.utc),
            status=status,
        )
        
        self._pending_orders[order_hash] = live_order
        return live_order

    def submit_orders(self, payloads: List[dict]) -> List[LiveOrder]:
        """Submit multiple orders."""
        orders = []
        for payload in payloads:
            order = self.submit_order(payload)
            orders.append(order)
        return orders

    def cancel_order(self, order_hash: str) -> None:
        """Cancel an order."""
        url = f"{self.base_url}/order/{order_hash}"
        
        try:
            response = requests.delete(
                url,
                headers=self._get_headers(),
                timeout=10,
            )
            response.raise_for_status()
            # Remove from pending orders
            self._pending_orders.pop(order_hash, None)
        except requests.RequestException as e:
            print(f"Error cancelling order {order_hash}: {e}")

    def cancel_unfilled_orders(self, orders: List[LiveOrder], timeout_seconds: int = 120) -> None:
        """Cancel orders that haven't filled within timeout."""
        current_time = datetime.now(timezone.utc)
        for order in orders:
            age_seconds = (current_time - order.created_at).total_seconds()
            if age_seconds > timeout_seconds and order.status not in ["filled", "cancelled"]:
                self.cancel_order(order.order_hash)

    def wait_for_fills(
        self,
        orders: List[LiveOrder],
        timeout_seconds: int = 60,
    ) -> List[FillEvent]:
        """Monitor orders until filled or timeout."""
        fills = []
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            for order in orders:
                if order.status == "filled":
                    # Query for fill details
                    fill = self._get_fill_details(order)
                    if fill:
                        fills.append(fill)
            
            # Check if all orders are filled or cancelled
            all_done = all(
                order.status in ["filled", "cancelled", "failed"]
                for order in orders
            )
            if all_done:
                break
            
            time.sleep(1)  # Poll every second
        
        return fills

    def _get_fill_details(self, order: LiveOrder) -> Optional[FillEvent]:
        """Get fill details for an order."""
        # In practice, you'd query the fills endpoint
        # For now, create a simplified fill event
        if order.status != "filled":
            return None
        
        return FillEvent(
            market_id=order.intent.market_id,
            order_hash=order.order_hash,
            side=order.intent.side,
            price=order.intent.price,
            size=order.intent.size,
            filled_at=datetime.now(timezone.utc),
        )

    def get_order_status(self, order_hash: str) -> Optional[str]:
        """Query order status."""
        url = f"{self.base_url}/order/{order_hash}"
        
        try:
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=10,
            )
            response.raise_for_status()
            order_data = response.json()
            return order_data.get("status")
        except requests.RequestException:
            return None
