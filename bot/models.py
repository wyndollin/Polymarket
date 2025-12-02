from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class MarketMetadata:
    id: str
    question: str
    outcome: str
    expiry: datetime
    tags: List[str]
    volume_24h: float
    is_active: bool


@dataclass
class OrderBookLevel:
    price: float
    size: float


@dataclass
class OrderBookSnapshot:
    market_id: str
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    best_bid: Optional[float]
    best_ask: Optional[float]
    last_trade_price: Optional[float]
    last_trade_time: Optional[datetime]
    liquidity_score: Optional[float]
    received_at: datetime


@dataclass
class OrderIntent:
    market_id: str
    side: Side
    price: float
    size: float
    ttl_seconds: int
    client_order_id: str
    metadata: Dict[str, str]


@dataclass
class LiveOrder:
    order_hash: str
    intent: OrderIntent
    created_at: datetime
    status: str


@dataclass
class FillEvent:
    market_id: str
    order_hash: str
    side: Side
    price: float
    size: float
    filled_at: datetime


@dataclass
class Position:
    market_id: str
    net_size: float
    avg_entry_price: float
    unrealized_pnl: float
    realized_pnl: float
