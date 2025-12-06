from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List, Optional
import json
import sqlite3
from pathlib import Path
from datetime import datetime

from bot.models import (
    LiveOrder,
    FillEvent,
    OrderBookSnapshot,
    Position,
    StraddlePosition,
    StraddleState,
)


class Persistence(ABC):
    """Abstract persistence layer for orders, fills, snapshots, and PnL."""

    @abstractmethod
    def save_orders(self, orders: Iterable[LiveOrder]) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_fills(self, fills: Iterable[FillEvent]) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_position(self, position: Position) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_straddle_position(self, position: StraddlePosition) -> None:
        """Save a straddle position."""
        raise NotImplementedError

    @abstractmethod
    def load_straddle_positions(self) -> List[StraddlePosition]:
        """Load all active straddle positions."""
        raise NotImplementedError

    @abstractmethod
    def get_straddle_position(self, market_id: str) -> Optional[StraddlePosition]:
        """Get a specific straddle position."""
        raise NotImplementedError


class InMemoryPersistence(Persistence):
    def __init__(self) -> None:
        self.orders: list[LiveOrder] = []
        self.fills: list[FillEvent] = []
        self.snapshots: list[OrderBookSnapshot] = []
        self.positions: list[Position] = []
        self.straddle_positions: dict[str, StraddlePosition] = {}

    def save_orders(self, orders: Iterable[LiveOrder]) -> None:
        self.orders.extend(list(orders))

    def save_fills(self, fills: Iterable[FillEvent]) -> None:
        self.fills.extend(list(fills))

    def save_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        self.snapshots.append(snapshot)

    def save_position(self, position: Position) -> None:
        self.positions.append(position)

    def save_straddle_position(self, position: StraddlePosition) -> None:
        self.straddle_positions[position.market_id] = position

    def load_straddle_positions(self) -> List[StraddlePosition]:
        return [
            pos for pos in self.straddle_positions.values()
            if pos.state != StraddleState.RESOLVED
        ]

    def get_straddle_position(self, market_id: str) -> Optional[StraddlePosition]:
        return self.straddle_positions.get(market_id)


class SqlitePersistence(Persistence):
    """SQLite-based persistence layer."""

    def __init__(self, db_path: str = "data/bot.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_hash TEXT PRIMARY KEY,
                market_id TEXT,
                side TEXT,
                price REAL,
                size REAL,
                ttl_seconds INTEGER,
                client_order_id TEXT,
                status TEXT,
                created_at TIMESTAMP,
                metadata TEXT
            )
        """)

        # Fills table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT,
                order_hash TEXT,
                side TEXT,
                price REAL,
                size REAL,
                filled_at TIMESTAMP
            )
        """)

        # Straddle positions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS straddle_positions (
                market_id TEXT PRIMARY KEY,
                yes_entry_price REAL,
                no_entry_price REAL,
                yes_size REAL,
                no_size REAL,
                cheap_side TEXT,
                favorite_side TEXT,
                state TEXT,
                entry_time TIMESTAMP,
                last_update_time TIMESTAMP,
                exit_price REAL,
                exit_time TIMESTAMP,
                realized_pnl REAL,
                unrealized_pnl REAL
            )
        """)

        # Trades table (completed trades with P/L)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT,
                entry_time TIMESTAMP,
                exit_time TIMESTAMP,
                realized_pnl REAL,
                final_outcome TEXT
            )
        """)

        conn.commit()
        conn.close()

    def save_orders(self, orders: Iterable[LiveOrder]) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()

        for order in orders:
            cursor.execute("""
                INSERT OR REPLACE INTO orders
                (order_hash, market_id, side, price, size, ttl_seconds,
                 client_order_id, status, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.order_hash,
                order.intent.market_id,
                order.intent.side.value,
                order.intent.price,
                order.intent.size,
                order.intent.ttl_seconds,
                order.intent.client_order_id,
                order.status,
                order.created_at.isoformat(),
                json.dumps(order.intent.metadata),
            ))

        conn.commit()
        conn.close()

    def save_fills(self, fills: Iterable[FillEvent]) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()

        for fill in fills:
            cursor.execute("""
                INSERT INTO fills
                (market_id, order_hash, side, price, size, filled_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                fill.market_id,
                fill.order_hash,
                fill.side.value,
                fill.price,
                fill.size,
                fill.filled_at.isoformat(),
            ))

        conn.commit()
        conn.close()

    def save_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        # Snapshots are not persisted to SQLite for now
        # Can be added if needed for analysis
        pass

    def save_position(self, position: Position) -> None:
        # Generic Position model not used for straddle strategy
        pass

    def save_straddle_position(self, position: StraddlePosition) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO straddle_positions
            (market_id, yes_entry_price, no_entry_price, yes_size, no_size,
             cheap_side, favorite_side, state, entry_time, last_update_time,
             exit_price, exit_time, realized_pnl, unrealized_pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            position.market_id,
            position.yes_entry_price,
            position.no_entry_price,
            position.yes_size,
            position.no_size,
            position.cheap_side,
            position.favorite_side,
            position.state.value,
            position.entry_time.isoformat(),
            position.last_update_time.isoformat(),
            position.exit_price,
            position.exit_time.isoformat() if position.exit_time else None,
            position.realized_pnl,
            position.unrealized_pnl,
        ))

        conn.commit()
        conn.close()

    def load_straddle_positions(self) -> List[StraddlePosition]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM straddle_positions
            WHERE state != ?
        """, (StraddleState.RESOLVED.value,))

        positions = []
        for row in cursor.fetchall():
            position = StraddlePosition(
                market_id=row["market_id"],
                yes_entry_price=row["yes_entry_price"],
                no_entry_price=row["no_entry_price"],
                yes_size=row["yes_size"],
                no_size=row["no_size"],
                cheap_side=row["cheap_side"],
                favorite_side=row["favorite_side"],
                state=StraddleState(row["state"]),
                entry_time=datetime.fromisoformat(row["entry_time"]),
                last_update_time=datetime.fromisoformat(row["last_update_time"]),
                exit_price=row["exit_price"],
                exit_time=datetime.fromisoformat(row["exit_time"]) if row["exit_time"] else None,
                realized_pnl=row["realized_pnl"],
                unrealized_pnl=row["unrealized_pnl"],
            )
            positions.append(position)

        conn.close()
        return positions

    def get_straddle_position(self, market_id: str) -> Optional[StraddlePosition]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM straddle_positions
            WHERE market_id = ?
        """, (market_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return StraddlePosition(
            market_id=row["market_id"],
            yes_entry_price=row["yes_entry_price"],
            no_entry_price=row["no_entry_price"],
            yes_size=row["yes_size"],
            no_size=row["no_size"],
            cheap_side=row["cheap_side"],
            favorite_side=row["favorite_side"],
            state=StraddleState(row["state"]),
            entry_time=datetime.fromisoformat(row["entry_time"]),
            last_update_time=datetime.fromisoformat(row["last_update_time"]),
            exit_price=row["exit_price"],
            exit_time=datetime.fromisoformat(row["exit_time"]) if row["exit_time"] else None,
            realized_pnl=row["realized_pnl"],
            unrealized_pnl=row["unrealized_pnl"],
        )
