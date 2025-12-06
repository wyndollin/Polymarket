"""
Fetch historical Valorant market data from Polymarket and save it for offline analysis.

This script:
- Uses the Gamma Markets API to discover Valorant markets.
- Uses the CLOB /prices-history endpoint to fetch historical prices per outcome token.
- Merges outcome price series into a per-match time series:
    market_id, ts, price_team_a, price_team_b, final_winner
- Writes the result to a CSV/Parquet file that can be consumed by
  `valorant_threshold_analysis.py`.

Notes:
- This is READ-ONLY: it does not place any orders or require private keys.
- It uses only public endpoints (no authentication required).
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json

import pandas as pd
import requests


GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
CLOB_BASE_URL = "https://clob.polymarket.com"


@dataclass
class ValorantMarket:
    id: str
    question: str
    clob_token_ids: List[str]
    outcomes: List[str]
    final_winner_index: Optional[int]


def _gamma_get(path: str, params: Optional[Dict] = None) -> dict:
    url = f"{GAMMA_BASE_URL}{path}"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _clob_get(path: str, params: Optional[Dict] = None) -> dict:
    url = f"{CLOB_BASE_URL}{path}"
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        # Print detailed error to help debug parameter issues (e.g. wrong market ID).
        print(
            f"Error from CLOB GET {url} "
            f"status={resp.status_code} "
            f"params={params} "
            f"body={resp.text}"
        )
        resp.raise_for_status()
    return resp.json()


def discover_valorant_markets(
    limit_per_page: int = 500,
    max_pages: int = 40,
    search_term: str = "valorant",
    only_closed: bool = False,
    verbose: bool = True,
) -> List[ValorantMarket]:
    """
    Use Gamma `GET /markets` to find Valorant-related markets.

    Strategy:
    - Page through markets (by default only closed/resolved).
    - Keep those where `sportsMarketType` (or `sports_market_type`) is "Valorant".
    - Require at least 2 outcome tokens (we use the first two for Team A/B).
    """
    markets: List[ValorantMarket] = []
    search_term_l = (search_term or "").lower()
    offset = 0

    for page in range(max_pages):
        params = {
            "limit": limit_per_page,
            "offset": offset,
        }
        # Prefer resolved (closed) markets for backtesting by default.
        if only_closed:
            params["closed"] = True

        data = _gamma_get("/markets", params=params)
        if not isinstance(data, list) or not data:
            break

        for m in data:
            # Filter by game/series metadata: seriesSlug 'valorant'
            series_slug = (m.get("seriesSlug") or "").lower()
            if series_slug != "valorant":
                continue

            # Optional loose filter on question text if the user provided a custom term.
            question = (m.get("question") or "").lower()
            if search_term_l and search_term_l != "valorant" and search_term_l not in question:
                continue

            clob_ids_raw = m.get("clobTokenIds") or m.get("clob_token_ids") or ""
            if not clob_ids_raw:
                continue

            # clobTokenIds may be:
            # - a JSON-encoded list string, e.g. '["id1","id2"]'
            # - a comma-separated string "id1,id2"
            # - an actual list
            if isinstance(clob_ids_raw, str):
                clob_ids_raw_str = clob_ids_raw.strip()
                if clob_ids_raw_str.startswith("["):
                    try:
                        parsed = json.loads(clob_ids_raw_str)
                        clob_token_ids = [str(x) for x in parsed]
                    except json.JSONDecodeError:
                        clob_token_ids = [s for s in clob_ids_raw_str.split(",") if s]
                else:
                    clob_token_ids = [s for s in clob_ids_raw_str.split(",") if s]
            elif isinstance(clob_ids_raw, list):
                clob_token_ids = [str(s) for s in clob_ids_raw]
            else:
                continue

            outcomes_raw = m.get("shortOutcomes") or m.get("outcomes") or ""
            if isinstance(outcomes_raw, str):
                # stored as comma-separated string
                outcomes = [s.strip() for s in outcomes_raw.split(",") if s.strip()]
            elif isinstance(outcomes_raw, list):
                outcomes = [str(s) for s in outcomes_raw]
            else:
                outcomes = []

            # Require at least 2 outcomes / token IDs; we will just use the first two.
            if len(clob_token_ids) < 2 or len(outcomes) < 2:
                continue

            # Try to infer final winner index from `outcomePrices` (1.0/0.0 pattern) or
            # from other resolution fields if present.
            final_winner_index: Optional[int] = None
            # In many resolved markets, lastTradePrice / outcomePrices will show 1.0 for the winner.
            outcome_prices_raw = m.get("outcomePrices") or ""
            prices: List[float] = []
            if isinstance(outcome_prices_raw, str):
                try:
                    prices = [float(x) for x in outcome_prices_raw.split(",")]
                except Exception:
                    prices = []
            elif isinstance(outcome_prices_raw, list):
                try:
                    prices = [float(x) for x in outcome_prices_raw]
                except Exception:
                    prices = []

            if len(prices) == 2:
                if prices[0] > prices[1]:
                    final_winner_index = 0
                elif prices[1] > prices[0]:
                    final_winner_index = 1

            market = ValorantMarket(
                id=str(m.get("id")),
                question=m.get("question") or "",
                clob_token_ids=clob_token_ids[:2],
                outcomes=outcomes[:2],
                final_winner_index=final_winner_index,
            )
            markets.append(market)

        if verbose:
            print(f"Fetched {len(data)} markets from Gamma (offset={offset})")

        offset += limit_per_page
        time.sleep(0.2)  # be nice to the API

    if verbose:
        print(f"Discovered {len(markets)} Valorant markets (2-outcome, resolved).")

    return markets


def discover_event_markets(
    event_slug: str,
    verbose: bool = True,
) -> List[ValorantMarket]:
    """
    Fetch markets associated with a specific event slug from Gamma.

    Example event slug (from Polymarket URL):
      https://polymarket.com/event/val-rrq1-geng-2025-12-03
      -> event_slug = "val-rrq1-geng-2025-12-03"

    We call:
      GET https://gamma-api.polymarket.com/markets?slug=<event_slug>

    and parse the returned markets.
    """
    data = _gamma_get("/markets", params={"slug": [event_slug]})
    markets_raw = data if isinstance(data, list) else []
    markets: List[ValorantMarket] = []
    for m in markets_raw:
        clob_ids_raw = m.get("clobTokenIds") or m.get("clob_token_ids") or ""
        if not clob_ids_raw:
            continue

        if isinstance(clob_ids_raw, str):
            clob_ids_raw_str = clob_ids_raw.strip()
            if clob_ids_raw_str.startswith("["):
                try:
                    parsed = json.loads(clob_ids_raw_str)
                    clob_token_ids = [str(x) for x in parsed]
                except json.JSONDecodeError:
                    clob_token_ids = [s for s in clob_ids_raw_str.split(",") if s]
            else:
                clob_token_ids = [s for s in clob_ids_raw_str.split(",") if s]
        elif isinstance(clob_ids_raw, list):
            clob_token_ids = [str(s) for s in clob_ids_raw]
        else:
            continue

        outcomes_raw = m.get("shortOutcomes") or m.get("outcomes") or ""
        if isinstance(outcomes_raw, str):
            outcomes = [s.strip() for s in outcomes_raw.split(",") if s.strip()]
        elif isinstance(outcomes_raw, list):
            outcomes = [str(s) for s in outcomes_raw]
        else:
            outcomes = []

        if len(clob_token_ids) < 2 or len(outcomes) < 2:
            continue

        final_winner_index: Optional[int] = None
        outcome_prices_raw = m.get("outcomePrices") or ""
        prices: List[float] = []
        if isinstance(outcome_prices_raw, str):
            try:
                prices = [float(x) for x in outcome_prices_raw.split(",")]
            except Exception:
                prices = []
        elif isinstance(outcome_prices_raw, list):
            try:
                prices = [float(x) for x in outcome_prices_raw]
            except Exception:
                prices = []

        if len(prices) == 2:
            if prices[0] > prices[1]:
                final_winner_index = 0
            elif prices[1] > prices[0]:
                final_winner_index = 1

        markets.append(
            ValorantMarket(
                id=str(m.get("id")),
                question=m.get("question") or "",
                clob_token_ids=clob_token_ids[:2],
                outcomes=outcomes[:2],
                final_winner_index=final_winner_index,
            )
        )

    if verbose:
        print(
            f"Discovered {len(markets)} markets for event slug '{event_slug}'."
        )

    return markets


def fetch_price_history_for_token(
    token_id: str,
    interval: str = "1m",
) -> pd.DataFrame:
    """
    Fetch price history for a single CLOB token using /prices-history.

    The Polymarket docs describe this as:
      GET /prices-history?market=<token_id>&interval=1m
    with response:
      { "history": [ { "t": unix_ts, "p": price }, ... ] }
    """
    params = {
        "market": token_id,
        "interval": interval,
    }
    # For minute-level intervals, Polymarket's CLOB API requires a minimum
    # `fidelity` (in minutes). Use 10 by default for 1m data.
    if interval.endswith("m"):
        params["fidelity"] = 10
    data = _clob_get("/prices-history", params=params)
    hist = data.get("history") or []

    if not hist:
        return pd.DataFrame(columns=["ts", "price"])

    df = pd.DataFrame(hist)
    # Expect columns "t" (unix timestamp), "p" (price)
    if "t" not in df or "p" not in df:
        return pd.DataFrame(columns=["ts", "price"])

    df["ts"] = df["t"].apply(
        lambda x: datetime.fromtimestamp(x, tz=timezone.utc).isoformat()
    )
    df.rename(columns={"p": "price"}, inplace=True)
    return df[["ts", "price"]]


def build_match_timeseries(
    market: ValorantMarket,
    interval: str = "1m",
    verbose: bool = True,
) -> Optional[pd.DataFrame]:
    """
    For a given ValorantMarket with 2 clob_token_ids, fetch price history for both
    sides and merge into a per-match time series.
    """
    if len(market.clob_token_ids) != 2:
        return None

    token_a, token_b = market.clob_token_ids

    if verbose:
        print(f"Fetching price history for market {market.id}: {market.question}")

    df_a = fetch_price_history_for_token(token_a, interval=interval)
    df_b = fetch_price_history_for_token(token_b, interval=interval)

    # Case 1: no history at all -> skip market.
    if df_a.empty and df_b.empty:
        if verbose:
            print(f"  Skipping market {market.id}: no history for either side.")
        return None

    # Case 2: both sides have history -> use them as-is.
    if not df_a.empty and not df_b.empty:
        df_a = df_a.rename(columns={"price": "price_team_a"})
        df_b = df_b.rename(columns={"price": "price_team_b"})
        merged = pd.merge(df_a, df_b, on="ts", how="outer").sort_values("ts")
    else:
        # Case 3: exactly one side has history. Treat that as the traded leg and
        # infer the other side as 1 - p (binary 2-outcome market assumption).
        if not df_a.empty:
            df_main = df_a.rename(columns={"price": "price_team_a"})
            merged = df_main.copy()
            merged["price_team_b"] = 1.0 - merged["price_team_a"]
        else:
            df_main = df_b.rename(columns={"price": "price_team_b"})
            merged = df_main.copy()
            merged["price_team_a"] = 1.0 - merged["price_team_b"]

        merged = merged.sort_values("ts")

    merged["market_id"] = market.id

    # Forward-fill prices to align sparse points
    merged[["price_team_a", "price_team_b"]] = merged[
        ["price_team_a", "price_team_b"]
    ].ffill()

    # Attach final_winner label ("A"/"B") if known
    if market.final_winner_index in (0, 1):
        merged["final_winner"] = "A" if market.final_winner_index == 0 else "B"
    else:
        merged["final_winner"] = None

    # Reorder columns
    merged = merged[["market_id", "ts", "price_team_a", "price_team_b", "final_winner"]]
    return merged


def run_data_pull(
    output_path: str | Path,
    interval: str = "1m",
    max_markets: Optional[int] = None,
    search_term: str = "valorant",
    event_slug: Optional[str] = None,
) -> Path:
    """
    High-level driver:
    - Discover Valorant markets via Gamma.
    - For each, build a merged per-match time series.
    - Concatenate and write to CSV/Parquet.
    """
    if event_slug:
        markets = discover_event_markets(event_slug=event_slug)
    else:
        markets = discover_valorant_markets(search_term=search_term)
    if max_markets is not None:
        markets = markets[:max_markets]

    all_rows: List[pd.DataFrame] = []
    for mkt in markets:
        ts_df = build_match_timeseries(mkt, interval=interval)
        if ts_df is not None and not ts_df.empty:
            all_rows.append(ts_df)

    if not all_rows:
        raise RuntimeError(
            "No historical time series built. "
            "Either no matching markets were found or /prices-history returned no data."
        )

    full_df = pd.concat(all_rows, ignore_index=True)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() == ".parquet":
        full_df.to_parquet(output_path, index=False)
    else:
        # Default to CSV
        full_df.to_csv(output_path, index=False)

    print(f"Wrote {len(full_df)} rows to {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Fetch historical Valorant market price data from Polymarket "
            "for offline exit-threshold analysis (no trading)."
        )
    )
    parser.add_argument(
        "--output",
        type=str,
        default="Strategy 2/Threshold Calculation/valorant_markets.csv",
        help="Path to output CSV/Parquet file (default: valorant_markets.csv).",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="1m",
        help="prices-history interval (e.g. 1m, 5m, 1h, 1d). Default: 1m",
    )
    parser.add_argument(
        "--max-markets",
        type=int,
        default=None,
        help="Optional cap on number of Valorant markets to process.",
    )
    parser.add_argument(
        "--search-term",
        type=str,
        default="valorant",
        help="Substring to search for in question/category/tags (default: 'valorant').",
    )
    parser.add_argument(
        "--event-slug",
        type=str,
        default=None,
        help=(
            "Optional Polymarket event slug, e.g. 'val-rrq1-geng-2025-12-03'. "
            "If provided, only markets for this event are pulled."
        ),
    )
    args = parser.parse_args()

    run_data_pull(
        output_path=args.output,
        interval=args.interval,
        max_markets=args.max_markets,
        search_term=args.search_term,
        event_slug=args.event_slug,
    )


