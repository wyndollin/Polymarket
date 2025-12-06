from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Iterable, List, Set
import time

import requests

from bot.config import Settings, ValorantStraddleConfig
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
    def __init__(self, settings: Settings, strategy_config: ValorantStraddleConfig) -> None:
        self.settings = settings
        self.strategy_config = strategy_config
        self._scanned_markets: Set[str] = set()  # Cache to avoid duplicates

    def scan(self) -> Iterable[MarketMetadata]:
        """Scan for Valorant markets that meet entry criteria."""
        url = f"{self.settings.gamma_base_url}/markets"
        
        # Build query parameters for Valorant markets
        params = {
            "active": "true",
            "tags": ",".join(self.strategy_config.valorant_tags),
        }
        
        print(f"Scanning markets from {url}...")
        try:
            response = requests.get(url, params=params, timeout=10)
            print(f"API response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            
            markets = []
            current_time = datetime.now(timezone.utc)
            
            for market_data in data:
                market_id = market_data.get("id")
                if not market_id or market_id in self._scanned_markets:
                    continue
                
                # Filter for match winner markets (YES/NO markets)
                question = market_data.get("question", "").lower()
                if "winner" not in question and "win" not in question:
                    continue
                
                # Check if market has YES/NO outcomes
                outcomes = market_data.get("outcomes", [])
                if len(outcomes) != 2:
                    continue
                
                # Check market age
                created_at = market_data.get("created_at")
                if created_at:
                    try:
                        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        age_seconds = (current_time - created_dt).total_seconds()
                        if age_seconds < self.strategy_config.min_market_age_seconds:
                            continue
                    except (ValueError, TypeError):
                        pass
                
                # Extract market metadata
                tags = market_data.get("tags", [])
                volume_24h = float(market_data.get("volume", {}).get("usd", 0) or 0)
                is_active = market_data.get("active", False)
                
                # Parse expiry if available
                expiry_str = market_data.get("end_date_iso")
                expiry = datetime.now(timezone.utc)
                if expiry_str:
                    try:
                        expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass
                
                metadata = MarketMetadata(
                    id=market_id,
                    question=market_data.get("question", ""),
                    outcome="",  # Not needed for entry filtering
                    expiry=expiry,
                    tags=tags,
                    volume_24h=volume_24h,
                    is_active=is_active,
                )
                
                markets.append(metadata)
                self._scanned_markets.add(market_id)
            
            return markets
            
        except requests.RequestException as e:
            # Log error but return empty list
            print(f"Error scanning markets: {e}")
            return []
