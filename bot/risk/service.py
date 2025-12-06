from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from bot.config import RiskSettings, ValorantStraddleConfig
from bot.models import Position, OrderIntent, StraddlePosition


class RiskManager(ABC):
    """Enforces exposure limits, daily loss limits, and forced unwind rules."""

    @abstractmethod
    def can_place(self, intent: OrderIntent) -> bool:
        raise NotImplementedError

    @abstractmethod
    def register_fill(self, position: Position) -> None:
        raise NotImplementedError

    @abstractmethod
    def can_enter_new_position(self, proposed_size: float) -> bool:
        """Check if a new position can be entered."""
        raise NotImplementedError

    @abstractmethod
    def calculate_position_size(self, bankroll: float) -> float:
        """Calculate max position size for new trade."""
        raise NotImplementedError

    @abstractmethod
    def get_current_exposure(self) -> float:
        """Get total current exposure."""
        raise NotImplementedError


class SimpleRiskManager(RiskManager):
    def __init__(
        self,
        settings: RiskSettings,
        strategy_config: ValorantStraddleConfig,
        bankroll: float = 1000.0,
    ) -> None:
        self.settings = settings
        self.strategy_config = strategy_config
        self.bankroll = bankroll
        self._active_positions: List[StraddlePosition] = []
        self._total_exposure: float = 0.0
        self._initial_bankroll = bankroll

    def can_place(self, intent: OrderIntent) -> bool:
        """Check if an order can be placed (basic check)."""
        # Check if order size exceeds per-market limit
        order_value = intent.price * intent.size
        if order_value > self.settings.max_exposure_per_market:
            return False
        return True

    def register_fill(self, position: Position) -> None:
        """Register a fill (for generic Position model)."""
        # Not used for straddle strategy
        pass

    def register_straddle_position(self, position: StraddlePosition) -> None:
        """Register a new straddle position."""
        self._active_positions.append(position)
        # Calculate exposure (total cost of entry)
        exposure = (
            position.yes_entry_price * position.yes_size +
            position.no_entry_price * position.no_size
        )
        self._total_exposure += exposure

    def unregister_straddle_position(self, position: StraddlePosition) -> None:
        """Unregister a resolved position."""
        if position in self._active_positions:
            self._active_positions.remove(position)
            # Recalculate total exposure
            self._total_exposure = sum(
                pos.yes_entry_price * pos.yes_size +
                pos.no_entry_price * pos.no_size
                for pos in self._active_positions
            )

    def can_enter_new_position(self, proposed_size: float) -> bool:
        """Check if a new position can be entered."""
        # Check max concurrent positions
        if len(self._active_positions) >= self.strategy_config.max_concurrent_positions:
            return False

        # Check total exposure limit
        new_exposure = self._total_exposure + proposed_size
        max_exposure = self.bankroll * (self.strategy_config.max_concurrent_positions * 
                                        self.strategy_config.position_size_pct)
        if new_exposure > max_exposure:
            return False

        # Check against risk settings
        if new_exposure > self.settings.max_total_exposure:
            return False

        return True

    def calculate_position_size(self, bankroll: float) -> float:
        """Calculate max position size for new trade."""
        self.bankroll = bankroll
        max_size = bankroll * self.strategy_config.position_size_pct
        
        # Ensure it doesn't exceed per-market limit
        max_size = min(max_size, self.settings.max_exposure_per_market)
        
        return max_size

    def get_current_exposure(self) -> float:
        """Get total current exposure."""
        return self._total_exposure

    def get_active_position_count(self) -> int:
        """Get number of active positions."""
        return len(self._active_positions)

    def check_drawdown(self) -> float:
        """Calculate current drawdown percentage."""
        if self._initial_bankroll == 0:
            return 0.0
        
        # Simplified: assume unrealized P/L affects bankroll
        total_unrealized = sum(pos.unrealized_pnl for pos in self._active_positions)
        current_bankroll = self.bankroll + total_unrealized
        drawdown = (self._initial_bankroll - current_bankroll) / self._initial_bankroll
        
        return max(0.0, drawdown)

    def should_pause_trading(self, drawdown_threshold: float = 0.20) -> bool:
        """Check if trading should be paused due to drawdown."""
        drawdown = self.check_drawdown()
        return drawdown >= drawdown_threshold
