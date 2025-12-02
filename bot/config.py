from __future__ import annotations

from dataclasses import dataclass
from typing import List
import os


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

    poly_address: str = os.getenv("POLY_ADDRESS", "")
    poly_api_key: str = os.getenv("POLY_API_KEY", "")
    poly_passphrase: str = os.getenv("POLY_PASSPHRASE", "")

    risk: RiskSettings = RiskSettings(
        max_exposure_per_market=100.0,
        max_total_exposure=1000.0,
        max_open_markets=20,
        max_order_ttl_seconds=120,
        min_spread_cents=3.0,
    )

    fee_model: FeeModel = FeeModel(
        maker_fee_bps=10.0,
        taker_fee_bps=20.0,
    )

    active_tags: List[str] = None
