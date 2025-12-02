from __future__ import annotations

"""Entry point CLI for running the Polymarket passive arbitrage bot.

This currently just wires together the high-level components in a very shallow way.
Real-time loops, async/websocket handling, and persistence are intentionally omitted
until strategy and risk parameters are finalized.
"""

from bot.config import Settings
from bot.market_scanner.service import GammaMarketScanner
from bot.orderbook_engine.service import InMemoryOrderbookEngine
from bot.strategy_engine.service import SimpleSpreadStrategy
from bot.order_builder.service import ClobOrderBuilder
from bot.execution_engine.service import RestExecutionEngine
from bot.fills.service import SimpleFillHandler
from bot.risk.service import SimpleRiskManager
from bot.persistence.service import InMemoryPersistence


def main() -> None:
    settings = Settings()

    scanner = GammaMarketScanner(settings)
    orderbooks = InMemoryOrderbookEngine(settings)
    strategy = SimpleSpreadStrategy(settings)
    builder = ClobOrderBuilder(settings)
    executor = RestExecutionEngine(settings)
    fills = SimpleFillHandler()
    risk = SimpleRiskManager(settings.risk)
    persistence = InMemoryPersistence()

    # Placeholder: a real implementation would run async loops here.
    print("Polymarket bot skeleton initialized.")


if __name__ == "__main__":
    main()
