from __future__ import annotations

"""Entry point CLI for running the Valorant volatility straddle bot."""

import asyncio
import signal
import sys
from datetime import datetime, timezone
from typing import List

from bot.config import Settings, ValorantStraddleConfig
from bot.market_scanner.service import GammaMarketScanner
from bot.orderbook_engine.service import InMemoryOrderbookEngine
from bot.strategy_engine.service import ValorantStraddleStrategy
from bot.order_builder.service import ClobOrderBuilder
from bot.execution_engine.service import RestExecutionEngine
from bot.risk.service import SimpleRiskManager
from bot.persistence.service import SqlitePersistence
from bot.positions.service import PositionTracker
from bot.models import StraddlePosition, StraddleState, LiveOrder


class ValorantStraddleBot:
    """Main bot orchestrator for Valorant straddle strategy."""

    def __init__(
        self,
        settings: Settings,
        strategy_config: ValorantStraddleConfig,
        bankroll: float = 1000.0,
        db_path: str = "data/bot.db",
    ) -> None:
        self.settings = settings
        self.strategy_config = strategy_config
        self.bankroll = bankroll
        self.running = False

        # Initialize components
        self.scanner = GammaMarketScanner(settings, strategy_config)
        self.orderbook = InMemoryOrderbookEngine(settings)
        self.strategy = ValorantStraddleStrategy(settings, strategy_config, bankroll)
        self.builder = ClobOrderBuilder(settings)
        self.executor = RestExecutionEngine(settings)
        self.risk = SimpleRiskManager(settings.risk, strategy_config, bankroll)
        self.persistence = SqlitePersistence(db_path)
        self.position_tracker = PositionTracker()

        # Track active markets
        self._active_markets: set[str] = set()

    async def initialize(self) -> None:
        """Initialize bot and load existing positions."""
        print("=" * 60)
        print("Initializing Valorant Straddle Bot...")
        print("=" * 60)
        
        print(f"Bankroll: ${self.bankroll:.2f}")
        print(f"Exit threshold: {self.strategy_config.exit_threshold * 100}%")
        print(f"Position size: {self.strategy_config.position_size_pct * 100}% per trade")
        print()

        # Load active positions from persistence
        print("Loading existing positions from database...")
        try:
            positions = self.persistence.load_straddle_positions()
            for position in positions:
                self.position_tracker._positions[position.market_id] = position
                self.risk.register_straddle_position(position)
                self.orderbook.subscribe_market(position.market_id)
                self._active_markets.add(position.market_id)
            print(f"✓ Loaded {len(positions)} active positions")
        except Exception as e:
            print(f"⚠ Error loading positions: {e}")
            positions = []
        
        print()

    async def scan_and_enter(self) -> None:
        """Scan for new markets and enter positions if conditions are met."""
        try:
            # Run scan in thread to avoid blocking
            markets = await asyncio.to_thread(self.scanner.scan)
            
            if markets:
                print(f"Found {len(markets)} qualifying markets")

            for market in markets:
                if market.id in self._active_markets:
                    continue

                # Get orderbook snapshot (simplified - would need actual API call)
                # For now, skip if we don't have orderbook data
                book = self.orderbook.get_snapshot(market.id)
                if not book:
                    # In real implementation, fetch orderbook from API
                    continue

                # Check entry conditions
                if not self.strategy.should_enter(market, book):
                    continue

                # Check risk limits
                position_size = self.risk.calculate_position_size(self.bankroll)
                if not self.risk.can_enter_new_position(position_size):
                    print(f"Risk limit reached, skipping market {market.id}")
                    continue

                # Generate entry orders
                entry_orders = self.strategy.generate_entry_orders(market, book)
                if not entry_orders:
                    continue

                # Build order payloads
                payloads = [self.builder.build(order.intent) for order in entry_orders]

                # Submit orders
                print(f"Entering position on market {market.id}")
                live_orders = self.executor.submit_orders(payloads)

                # Wait for fills
                fills = await asyncio.to_thread(
                    self.executor.wait_for_fills,
                    live_orders,
                    timeout_seconds=60,
                )

                # Check if both sides filled
                if len(fills) == 2:
                    # Create position
                    yes_order = next((o for o in live_orders if "yes" in o.intent.client_order_id), None)
                    no_order = next((o for o in live_orders if "no" in o.intent.client_order_id), None)

                    if yes_order and no_order:
                        position = self.position_tracker.create_position(
                            market.id,
                            yes_order,
                            no_order,
                        )
                        self.risk.register_straddle_position(position)
                        self.persistence.save_straddle_position(position)
                        self.orderbook.subscribe_market(market.id)
                        self._active_markets.add(market.id)
                        print(f"Position entered: {market.id}")
                else:
                    # Partial fill - cancel unfilled orders
                    print(f"Partial fill on {market.id}, cancelling unfilled orders")
                    for order in live_orders:
                        if order.status != "filled":
                            self.executor.cancel_order(order.order_hash)

        except Exception as e:
            print(f"Error in scan_and_enter: {e}")

    async def check_exits(self) -> None:
        """Check active positions for exit conditions."""
        try:
            active_positions = self.position_tracker.get_active_positions()

            for position in active_positions:
                if position.state != StraddleState.ENTERED:
                    continue

                # Get current orderbook
                book = self.orderbook.get_snapshot(position.market_id)
                if not book:
                    continue

                # Update position state
                position = self.strategy.update_position_state(position, book)

                # Check for exit
                exit_orders = self.strategy.check_exits(position, book)
                if exit_orders:
                    # Build and submit exit order
                    payload = self.builder.build(exit_orders[0].intent)
                    live_order = self.executor.submit_order(payload)

                    # Wait for fill
                    fills = await asyncio.to_thread(
                        self.executor.wait_for_fills,
                        [live_order],
                        timeout_seconds=30,
                    )

                    if fills:
                        # Update position
                        position = self.position_tracker.update_position_from_fill(
                            position,
                            fills[0],
                        )
                        self.persistence.save_straddle_position(position)
                        self.persistence.save_fills(fills)
                        print(f"Exit executed for {position.market_id} at {position.exit_price}")

        except Exception as e:
            print(f"Error in check_exits: {e}")

    async def process_fills(self) -> None:
        """Process any new fills and update positions."""
        # This would poll for new fills or be called by WebSocket handlers
        # For now, handled in scan_and_enter and check_exits
        pass

    async def run(self) -> None:
        """Main event loop."""
        await self.initialize()

        self.running = True
        print("=" * 60)
        print("Bot started. Press Ctrl+C to stop.")
        print("=" * 60)
        print()

        iteration = 0
        while self.running:
            iteration += 1
            if iteration % 12 == 0:  # Every minute (12 * 5 seconds)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Bot running... Active positions: {len(self.position_tracker.get_active_positions())}")
            try:
                # Check for new entries
                await self.scan_and_enter()

                # Check for exits
                await self.check_exits()

                # Process fills
                await self.process_fills()

                # Sleep before next iteration
                await asyncio.sleep(5)  # Poll every 5 seconds

            except KeyboardInterrupt:
                print("\nShutting down...")
                self.running = False
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                await asyncio.sleep(5)

        # Graceful shutdown
        await self.shutdown()

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        print("Shutting down bot...")

        # Cancel pending orders
        active_positions = self.position_tracker.get_active_positions()
        for position in active_positions:
            # In real implementation, cancel any pending orders
            pass

        # Persist final state
        for position in active_positions:
            self.persistence.save_straddle_position(position)

        print("Shutdown complete.")


def main() -> None:
    """Main entry point."""
    settings = Settings()
    strategy_config = ValorantStraddleConfig()
    bankroll = 1000.0  # Default bankroll, should come from config

    bot = ValorantStraddleBot(
        settings=settings,
        strategy_config=strategy_config,
        bankroll=bankroll,
    )

    # Run async main loop
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\nBot stopped by user.")


if __name__ == "__main__":
    main()
