"""Tests for Position Tracker."""

import pytest
from datetime import datetime, timezone

from bot.positions.service import PositionTracker
from bot.models import LiveOrder, OrderIntent, Side, FillEvent, StraddleState


@pytest.fixture
def tracker():
    return PositionTracker()


@pytest.fixture
def yes_order():
    intent = OrderIntent(
        market_id="test-market-YES",
        side=Side.BUY,
        price=0.50,
        size=100.0,
        ttl_seconds=120,
        client_order_id="test-yes-1",
        metadata={},
    )
    return LiveOrder(
        order_hash="yes-hash-1",
        intent=intent,
        created_at=datetime.now(timezone.utc),
        status="filled",
    )


@pytest.fixture
def no_order():
    intent = OrderIntent(
        market_id="test-market-NO",
        side=Side.BUY,
        price=0.50,
        size=100.0,
        ttl_seconds=120,
        client_order_id="test-no-1",
        metadata={},
    )
    return LiveOrder(
        order_hash="no-hash-1",
        intent=intent,
        created_at=datetime.now(timezone.utc),
        status="filled",
    )


def test_create_position(tracker, yes_order, no_order):
    """Test position creation."""
    position = tracker.create_position("test-market-1", yes_order, no_order)
    
    assert position.market_id == "test-market-1"
    assert position.yes_entry_price == 0.50
    assert position.no_entry_price == 0.50
    assert position.state == StraddleState.ENTERED
    assert position.cheap_side in ["YES", "NO"]


def test_get_active_positions(tracker, yes_order, no_order):
    """Test getting active positions."""
    position1 = tracker.create_position("test-market-1", yes_order, no_order)
    position2 = tracker.create_position("test-market-2", yes_order, no_order)
    
    active = tracker.get_active_positions()
    assert len(active) == 2
    assert position1 in active
    assert position2 in active


def test_update_position_from_exit_fill(tracker, yes_order, no_order):
    """Test updating position with exit fill."""
    position = tracker.create_position("test-market-1", yes_order, no_order)
    
    # Create exit fill
    exit_fill = FillEvent(
        market_id="test-market-1-YES",
        order_hash="exit-hash-1",
        side=Side.SELL,
        price=0.18,
        size=100.0,
        filled_at=datetime.now(timezone.utc),
    )
    
    updated = tracker.update_position_from_fill(position, exit_fill)
    assert updated.state == StraddleState.EXITED
    assert updated.exit_price == 0.18
    assert updated.exit_time is not None


def test_resolve_position(tracker, yes_order, no_order):
    """Test position resolution."""
    position = tracker.create_position("test-market-1", yes_order, no_order)
    
    resolved = tracker.resolve_position(position, "YES")
    assert resolved.state == StraddleState.RESOLVED

