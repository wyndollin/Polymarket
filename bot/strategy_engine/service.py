from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List, Optional
from datetime import datetime, timezone
import uuid

from bot.config import Settings, RiskSettings, FeeModel, ValorantStraddleConfig
from bot.models import (
    MarketMetadata,
    OrderBookSnapshot,
    OrderIntent,
    Side,
    StraddlePosition,
    StraddleState,
)


class StrategyEngine(ABC):
    """Decides whether to place orders, and if so, side/price/size/TTL.

    Inputs:
    - Orderbook snapshot
    - Market metadata
    - Risk settings
    - Fee model
    - Latency stats (to be added later)
    """

    @abstractmethod
    def generate_order_intents(
        self,
        market: MarketMetadata,
        book: OrderBookSnapshot,
    ) -> List[OrderIntent]:
        raise NotImplementedError


class SimpleSpreadStrategy(StrategyEngine):
    """Very basic placeholder strategy.

    For now, this only illustrates the interface and does not place real orders.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.risk: RiskSettings = settings.risk
        self.fees: FeeModel = settings.fee_model

    def generate_order_intents(
        self,
        market: MarketMetadata,
        book: OrderBookSnapshot,
    ) -> List[OrderIntent]:
        return []


class ValorantStraddleStrategy(StrategyEngine):
    """Valorant volatility straddle strategy with single threshold exit at 18%."""

    def __init__(
        self,
        settings: Settings,
        strategy_config: ValorantStraddleConfig,
        bankroll: float = 1000.0,
    ) -> None:
        self.settings = settings
        self.strategy_config = strategy_config
        self.bankroll = bankroll
        self.risk: RiskSettings = settings.risk
        self.fees: FeeModel = settings.fee_model

    def should_enter(self, market: MarketMetadata, book: OrderBookSnapshot) -> bool:
        """Check if market meets entry conditions (both sides near 0.5)."""
        if not book:
            return False
        
        # Get YES and NO prices
        # In practice, you'd query separate orderbooks for YES and NO outcomes
        # For now, simplified check using best_ask
        if book.best_ask is None:
            return False
        
        yes_price = book.best_ask
        no_price = 1.0 - yes_price  # Assuming they sum to 1.0
        
        # Check if both sides are within tolerance of 0.5
        tolerance = self.strategy_config.entry_price_tolerance
        yes_near_50 = abs(yes_price - 0.5) <= tolerance
        no_near_50 = abs(no_price - 0.5) <= tolerance
        
        return yes_near_50 and no_near_50

    def generate_entry_orders(
        self,
        market: MarketMetadata,
        book: OrderBookSnapshot,
    ) -> List[OrderIntent]:
        """Generate entry orders: buy both YES and NO."""
        if not self.should_enter(market, book):
            return []
        
        # Calculate position size
        position_size = self.bankroll * self.strategy_config.position_size_pct
        
        # Get current prices (use best_ask for buying)
        yes_price = book.best_ask or 0.5
        no_price = 1.0 - yes_price
        
        # Calculate sizes for each side (equal dollar amounts)
        yes_size = position_size / yes_price
        no_size = position_size / no_price
        
        # Generate order intents
        base_order_id = str(uuid.uuid4())
        
        yes_order = OrderIntent(
            market_id=f"{market.id}-YES",  # YES outcome market ID
            side=Side.BUY,
            price=yes_price,
            size=yes_size,
            ttl_seconds=self.settings.risk.max_order_ttl_seconds,
            client_order_id=f"{base_order_id}-yes",
            metadata={"strategy": "valorant_straddle", "type": "entry", "side": "yes"},
        )
        
        no_order = OrderIntent(
            market_id=f"{market.id}-NO",  # NO outcome market ID
            side=Side.BUY,
            price=no_price,
            size=no_size,
            ttl_seconds=self.settings.risk.max_order_ttl_seconds,
            client_order_id=f"{base_order_id}-no",
            metadata={"strategy": "valorant_straddle", "type": "entry", "side": "no"},
        )
        
        return [yes_order, no_order]

    def check_exits(
        self,
        position: StraddlePosition,
        book: OrderBookSnapshot,
    ) -> List[OrderIntent]:
        """Check if exit conditions are met and generate exit orders."""
        if position.state != StraddleState.ENTERED:
            return []
        
        if not book:
            return []
        
        # Get current cheap side price
        cheap_price = book.best_ask  # Simplified - would need actual cheap side price
        if cheap_price is None:
            return []
        
        # Check if threshold crossed
        threshold = self.strategy_config.exit_threshold
        if cheap_price <= threshold:
            # Generate sell order for 100% of cheap side
            exit_order = OrderIntent(
                market_id=position.market_id,
                side=Side.SELL,
                price=cheap_price,
                size=position.yes_size if position.cheap_side == "YES" else position.no_size,
                ttl_seconds=self.settings.risk.max_order_ttl_seconds,
                client_order_id=f"exit-{position.market_id}-{uuid.uuid4()}",
                metadata={
                    "strategy": "valorant_straddle",
                    "type": "exit",
                    "threshold": threshold,
                    "cheap_side": position.cheap_side,
                },
            )
            return [exit_order]
        
        return []

    def update_position_state(
        self,
        position: StraddlePosition,
        book: OrderBookSnapshot,
    ) -> StraddlePosition:
        """Update position state based on current prices."""
        if position.state == StraddleState.RESOLVED:
            return position
        
        # Identify cheap side and favorite
        if book.best_ask is not None:
            yes_price = book.best_ask
            no_price = 1.0 - yes_price
            
            if yes_price < no_price:
                position.cheap_side = "YES"
                position.favorite_side = "NO"
            else:
                position.cheap_side = "NO"
                position.favorite_side = "YES"
        
        position.last_update_time = datetime.now(timezone.utc)
        return position

    def generate_order_intents(
        self,
        market: MarketMetadata,
        book: OrderBookSnapshot,
    ) -> List[OrderIntent]:
        """Main entry point - generates orders based on market state."""
        # This method is for entry only
        # Exit logic is handled separately via check_exits
        return self.generate_entry_orders(market, book)
