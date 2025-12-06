from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import os
import yaml


@dataclass
class RiskSettings:
    max_exposure_per_market: float
    max_total_exposure: float
    max_open_markets: int
    max_order_ttl_seconds: int
    min_spread_cents: float


@dataclass
class FeeModel:
    maker_fee_bps: float
    taker_fee_bps: float


@dataclass
class Settings:
    gamma_base_url: str = os.getenv("GAMMA_BASE_URL", "https://gamma-api.polymarket.com")
    clob_base_url: str = os.getenv("CLOB_BASE_URL", "https://clob.polymarket.com")
    clob_ws_url: str = os.getenv("CLOB_WS_URL", "wss://ws-subscriptions-clob.polymarket.com/ws/")

    poly_api_key: str = os.getenv("POLY_API_KEY", "")
    poly_api_secret: str = os.getenv("POLY_API_SECRET", "")
    poly_api_passphrase: str = os.getenv("POLY_API_PASSPHRASE", "")

    risk: RiskSettings = field(default_factory=lambda: RiskSettings(
        max_exposure_per_market=100.0,
        max_total_exposure=1000.0,
        max_open_markets=20,
        max_order_ttl_seconds=120,
        min_spread_cents=3.0,
    ))

    fee_model: FeeModel = field(default_factory=lambda: FeeModel(
        maker_fee_bps=10.0,
        taker_fee_bps=20.0,
    ))

    active_tags: Optional[List[str]] = None


@dataclass
class ValorantStraddleConfig:
    """Configuration for Valorant volatility straddle strategy."""
    entry_price_tolerance: float = 0.05  # Both sides within 0.45-0.55
    exit_threshold: float = 0.18  # Single threshold: sell 100% of cheap side when price <= 0.18
    min_market_age_seconds: int = 300  # Avoid entering too early
    position_size_pct: float = 0.03  # 3% of bankroll per trade
    max_concurrent_positions: int = 5
    valorant_tags: List[str] = field(default_factory=lambda: ["valorant", "esports"])

    @classmethod
    def from_yaml(cls, config_path: Optional[str] = None) -> ValorantStraddleConfig:
        """Load configuration from YAML file."""
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        
        config_path = Path(config_path)
        if not config_path.exists():
            # Return default config if file doesn't exist
            return cls()
        
        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f)
        
        strategy_config = config_data.get("strategy", {})
        entry_config = strategy_config.get("entry", {})
        exit_config = strategy_config.get("exit", {})
        position_config = strategy_config.get("position_sizing", {})
        filter_config = strategy_config.get("market_filtering", {})
        
        return cls(
            entry_price_tolerance=entry_config.get("price_tolerance", 0.05),
            exit_threshold=exit_config.get("threshold", 0.18),
            min_market_age_seconds=entry_config.get("min_market_age_seconds", 300),
            position_size_pct=position_config.get("position_size_pct", 0.03),
            max_concurrent_positions=position_config.get("max_concurrent_positions", 5),
            valorant_tags=filter_config.get("valorant_tags", ["valorant", "esports"]),
        )
