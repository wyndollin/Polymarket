"""Tests for Valorant Straddle Strategy."""

import pytest
from datetime import datetime, timezone

from bot.models import MarketMetadata, OrderBookSnapshot, OrderBookLevel, StraddlePosition, StraddleState
from bot.config import Settings, ValorantStraddleConfig
from bot.strategy_engine.service import ValorantStraddleStrategy


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def strategy_config():
    return ValorantStraddleConfig()


@pytest.fixture
def strategy(settings, strategy_config):
    return ValorantStraddleStrategy(settings, strategy_config, bankroll=1000.0)


@pytest.fixture
def market_metadata():
    return MarketMetadata(
        id="test-market-1",
        question="Will Team A win?",
        outcome="",
        expiry=datetime.now(timezone.utc),
        tags=["valorant", "esports"],
        volume_24h=1000.0,
        is_active=True,
    )


@pytest.fixture
def orderbook_50_50():
    """Orderbook with both sides at 0.5."""
    return OrderBookSnapshot(
        market_id="test-market-1",
        bids=[OrderBookLevel(price=0.49, size=100.0)],
        asks=[OrderBookLevel(price=0.51, size=100.0)],
        best_bid=0.49,
        best_ask=0.51,
        last_trade_price=0.50,
        last_trade_time=datetime.now(timezone.utc),
        liquidity_score=1.0,
        received_at=datetime.now(timezone.utc),
    )


def test_should_enter_near_50_50(strategy, market_metadata, orderbook_50_50):
    """Test that entry is allowed when both sides are near 0.5."""
    assert strategy.should_enter(market_metadata, orderbook_50_50) is True


def test_should_not_enter_far_from_50_50(strategy, market_metadata):
    """Test that entry is not allowed when sides are far from 0.5."""
    orderbook = OrderBookSnapshot(
        market_id="test-market-1",
        bids=[OrderBookLevel(price=0.30, size=100.0)],
        asks=[OrderBookLevel(price=0.70, size=100.0)],
        best_bid=0.30,
        best_ask=0.70,
        last_trade_price=0.50,
        last_trade_time=datetime.now(timezone.utc),
        liquidity_score=1.0,
        received_at=datetime.now(timezone.utc),
    )
    assert strategy.should_enter(market_metadata, orderbook) is False


def test_generate_entry_orders(strategy, market_metadata, orderbook_50_50):
    """Test entry order generation."""
    orders = strategy.generate_entry_orders(market_metadata, orderbook_50_50)
    assert len(orders) == 2  # YES and NO orders
    assert orders[0].side.value == "BUY"
    assert orders[1].side.value == "BUY"


def test_check_exits_threshold_crossed(strategy):
    """Test exit detection when threshold is crossed."""
    position = StraddlePosition(
        market_id="test-market-1",
        yes_entry_price=0.50,
        no_entry_price=0.50,
        yes_size=100.0,
        no_size=100.0,
        cheap_side="YES",
        favorite_side="NO",
        state=StraddleState.ENTERED,
        entry_time=datetime.now(timezone.utc),
        last_update_time=datetime.now(timezone.utc),
    )
    
    # Orderbook with cheap side at 0.17 (below threshold)
    orderbook = OrderBookSnapshot(
        market_id="test-market-1",
        bids=[OrderBookLevel(price=0.16, size=100.0)],
        asks=[OrderBookLevel(price=0.17, size=100.0)],
        best_bid=0.16,
        best_ask=0.17,
        last_trade_price=0.17,
        last_trade_time=datetime.now(timezone.utc),
        liquidity_score=1.0,
        received_at=datetime.now(timezone.utc),
    )
    
    exit_orders = strategy.check_exits(position, orderbook)
    assert len(exit_orders) == 1
    assert exit_orders[0].side.value == "SELL"


def test_check_exits_threshold_not_crossed(strategy):
    """Test that no exit is generated when threshold not crossed."""
    position = StraddlePosition(
        market_id="test-market-1",
        yes_entry_price=0.50,
        no_entry_price=0.50,
        yes_size=100.0,
        no_size=100.0,
        cheap_side="YES",
        favorite_side="NO",
        state=StraddleState.ENTERED,
        entry_time=datetime.now(timezone.utc),
        last_update_time=datetime.now(timezone.utc),
    )
    
    # Orderbook with cheap side at 0.25 (above threshold)
    orderbook = OrderBookSnapshot(
        market_id="test-market-1",
        bids=[OrderBookLevel(price=0.24, size=100.0)],
        asks=[OrderBookLevel(price=0.25, size=100.0)],
        best_bid=0.24,
        best_ask=0.25,
        last_trade_price=0.25,
        last_trade_time=datetime.now(timezone.utc),
        liquidity_score=1.0,
        received_at=datetime.now(timezone.utc),
    )
    
    exit_orders = strategy.check_exits(position, orderbook)
    assert len(exit_orders) == 0

