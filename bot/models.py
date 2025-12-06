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


class StraddleState(str, Enum):
    """State machine for straddle positions."""
    WAITING_ENTRY = "WAITING_ENTRY"
    ENTERED = "ENTERED"
    EXITED = "EXITED"
    RESOLVED = "RESOLVED"


@dataclass
class StraddlePosition:
    """Tracks a straddle position for the Valorant volatility strategy."""
    market_id: str
    yes_entry_price: float
    no_entry_price: float
    yes_size: float
    no_size: float
    cheap_side: str  # "YES" or "NO"
    favorite_side: str  # Opposite of cheap_side
    state: StraddleState
    entry_time: datetime
    last_update_time: datetime
    exit_price: Optional[float] = None  # Price at which cheap side was sold
    exit_time: Optional[datetime] = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
