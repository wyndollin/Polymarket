from __future__ import annotations

from typing import Dict, List, Optional
from datetime import datetime, timezone

from bot.models import (
    StraddlePosition,
    StraddleState,
    LiveOrder,
    FillEvent,
    OrderIntent,
)


class PositionTracker:
    """Tracks active straddle positions and calculates P/L."""

    def __init__(self) -> None:
        self._positions: Dict[str, StraddlePosition] = {}

    def create_position(
        self,
        market_id: str,
        yes_order: LiveOrder,
        no_order: LiveOrder,
    ) -> StraddlePosition:
        """Create a new straddle position from filled entry orders."""
        # Determine which side is cheaper (for future exit logic)
        yes_price = yes_order.intent.price
        no_price = no_order.intent.price
        
        if yes_price < no_price:
            cheap_side = "YES"
            favorite_side = "NO"
        else:
            cheap_side = "NO"
            favorite_side = "YES"
        
        position = StraddlePosition(
            market_id=market_id,
            yes_entry_price=yes_price,
            no_entry_price=no_price,
            yes_size=yes_order.intent.size,
            no_size=no_order.intent.size,
            cheap_side=cheap_side,
            favorite_side=favorite_side,
            state=StraddleState.ENTERED,
            entry_time=datetime.now(timezone.utc),
            last_update_time=datetime.now(timezone.utc),
        )
        
        self._positions[market_id] = position
        return position

    def update_position_from_fill(
        self,
        position: StraddlePosition,
        fill: FillEvent,
    ) -> StraddlePosition:
        """Update position when a fill occurs (entry or exit)."""
        # Update last update time
        position.last_update_time = datetime.now(timezone.utc)
        
        # If this is an exit fill (selling cheap side)
        if position.state == StraddleState.ENTERED:
            # Check if this is selling the cheap side
            fill_side = fill.side.name if hasattr(fill.side, 'name') else str(fill.side)
            if (fill_side == "SELL" and 
                ((position.cheap_side == "YES" and "yes" in fill.market_id.lower()) or
                 (position.cheap_side == "NO" and "no" in fill.market_id.lower()))):
                # Exit fill
                position.exit_price = fill.price
                position.exit_time = fill.filled_at
                position.state = StraddleState.EXITED
                
                # Calculate realized P/L from exit
                if position.cheap_side == "YES":
                    realized_loss = (position.yes_entry_price - fill.price) * fill.size
                else:
                    realized_loss = (position.no_entry_price - fill.price) * fill.size
                position.realized_pnl = realized_loss
        
        return position

    def get_active_positions(self) -> List[StraddlePosition]:
        """Get all active positions (not resolved)."""
        return [
            pos for pos in self._positions.values()
            if pos.state != StraddleState.RESOLVED
        ]

    def get_position(self, market_id: str) -> Optional[StraddlePosition]:
        """Get position by market ID."""
        return self._positions.get(market_id)

    def resolve_position(
        self,
        position: StraddlePosition,
        final_outcome: str,  # "YES" or "NO"
    ) -> StraddlePosition:
        """Mark position as resolved and calculate final P/L."""
        position.state = StraddleState.RESOLVED
        position.last_update_time = datetime.now(timezone.utc)
        
        # Calculate final P/L
        # If favorite won, we get full payout on favorite side
        # We already realized loss on cheap side exit
        if position.favorite_side == final_outcome:
            # Favorite won - calculate gain
            if position.favorite_side == "YES":
                favorite_payout = position.yes_size * 1.0  # Full payout
                favorite_cost = position.yes_entry_price * position.yes_size
            else:
                favorite_payout = position.no_size * 1.0
                favorite_cost = position.no_entry_price * position.no_size
            
            favorite_gain = favorite_payout - favorite_cost
            position.realized_pnl += favorite_gain
        else:
            # Favorite lost - we already took the loss on cheap side exit
            # No additional gain
            pass
        
        return position

    def calculate_unrealized_pnl(
        self,
        position: StraddlePosition,
        current_yes_price: Optional[float],
        current_no_price: Optional[float],
    ) -> float:
        """Calculate unrealized P/L based on current prices."""
        if position.state != StraddleState.ENTERED:
            return position.realized_pnl
        
        if current_yes_price is None or current_no_price is None:
            return 0.0
        
        # Calculate current value of positions
        yes_value = current_yes_price * position.yes_size
        no_value = current_no_price * position.no_size
        
        # Calculate cost basis
        yes_cost = position.yes_entry_price * position.yes_size
        no_cost = position.no_entry_price * position.no_size
        
        unrealized = (yes_value + no_value) - (yes_cost + no_cost)
        position.unrealized_pnl = unrealized
        
        return unrealized

    def remove_position(self, market_id: str) -> None:
        """Remove a position (after resolution or cancellation)."""
        self._positions.pop(market_id, None)

