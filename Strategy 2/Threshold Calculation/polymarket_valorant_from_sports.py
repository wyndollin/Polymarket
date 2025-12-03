"""
Discover and pull ALL Valorant markets using the sports metadata + markets filters.

This script keeps the original per-slug puller untouched and instead:
1) Uses /sports to find the Valorant sport and its tag IDs.
2) Uses /markets?tag_id=...&related_tags=true to enumerate Valorant markets.
3) Reuses the existing price-history logic to build a combined CSV.

Output goes under `Strategy 2/Threshold Calculation/Pulled Data/`.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

import pandas as pd

from polymarket_valorant_data_pull import (  # type: ignore
    ValorantMarket,
    _gamma_get,
    build_match_timeseries,
)


VALORANT_TAG_ID = 101672  # from /sports entry where sport == "valorant"


def discover_valorant_markets_by_tag(
    tag_id: int = VALORANT_TAG_ID,
    limit_per_page: int = 500,
    max_pages: int = 40,
    closed_only: bool = False,
    verbose: bool = True,
) -> List[ValorantMarket]:
    """
    Use Gamma `GET /markets?tag_id=...&related_tags=true` to discover Valorant markets.

    We rely on the sports metadata:
      GET /sports -> entry where sport == "valorant" -> tags includes 101672

    That tag_id appears to correspond to Valorant esports.
    """
    markets: List[ValorantMarket] = []
    offset = 0

    for page in range(max_pages):
        params = {
            "limit": limit_per_page,
            "offset": offset,
            "tag_id": tag_id,
            "related_tags": True,
        }
        if closed_only:
            params["closed"] = True

        data = _gamma_get("/markets", params=params)
        if not isinstance(data, list) or not data:
            break

        for m in data:
            question = (m.get("question") or "").lower()
            # Sanity filter: keep only Valorant-labeled questions
            if "valorant" not in question:
                continue

            clob_ids_raw = m.get("clobTokenIds") or m.get("clob_token_ids") or ""
            if not clob_ids_raw:
                continue

            # clobTokenIds is JSON-encoded list string in Gamma
            import json  # local import to avoid polluting global namespace

            if isinstance(clob_ids_raw, str):
                raw = clob_ids_raw.strip()
                if raw.startswith("["):
                    try:
                        parsed = json.loads(raw)
                        clob_token_ids = [str(x) for x in parsed]
                    except json.JSONDecodeError:
                        clob_token_ids = [s for s in raw.split(",") if s]
                else:
                    clob_token_ids = [s for s in raw.split(",") if s]
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

            # Infer winner index if possible (same heuristic as original script)
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
            print(f"Fetched {len(data)} markets from Gamma (offset={offset})")

        offset += limit_per_page

    if verbose:
        print(f"Discovered {len(markets)} Valorant markets via tag_id={tag_id}.")

    # Deduplicate by market_id
    dedup: dict[str, ValorantMarket] = {}
    for m in markets:
        dedup[m.id] = m

    return list(dedup.values())


def pull_all_valorant_markets(
    output_path: str | Path,
    interval: str = "1m",
    closed_only: bool = False,
) -> Path:
    """
    Discover all Valorant markets via sports tag, then pull their price histories
    into a single CSV/Parquet file.
    """
    markets = discover_valorant_markets_by_tag(closed_only=closed_only)
    if not markets:
        raise RuntimeError("No Valorant markets discovered via sports tag.")

    all_rows: list[pd.DataFrame] = []
    for m in markets:
        ts_df = build_match_timeseries(market=m, interval=interval)
        if ts_df is not None and not ts_df.empty:
            all_rows.append(ts_df)

    if not all_rows:
        raise RuntimeError(
            "No historical time series built for any Valorant market discovered via sports tag."
        )

    full_df = pd.concat(all_rows, ignore_index=True)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".parquet":
        full_df.to_parquet(out, index=False)
    else:
        full_df.to_csv(out, index=False)

    print(f"Wrote {len(full_df)} rows across {len(markets)} markets to {out}")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Discover all Valorant markets via sports metadata and pull "
            "their price histories into a single CSV/Parquet file."
        )
    )
    parser.add_argument(
        "--output",
        type=str,
        default="Strategy 2/Threshold Calculation/Pulled Data/valorant_markets_all.csv",
        help="Output CSV/Parquet path (default: valorant_markets_all.csv in Pulled Data).",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="1m",
        help="prices-history interval (e.g. 1m, 5m, 1h, 1d). Default: 1m",
    )
    parser.add_argument(
        "--closed-only",
        action="store_true",
        help="If set, only include closed (resolved) Valorant markets.",
    )
    args = parser.parse_args()

    pull_all_valorant_markets(
        output_path=args.output,
        interval=args.interval,
        closed_only=args.closed_only,
    )


