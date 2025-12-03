"""
Enrich Valorant time-series CSV with authoritative winner and team names.

Pipeline:
- Input: valorant_markets_closed.csv with columns:
    market_id, ts, price_team_a, price_team_b, final_winner
- For each unique market_id:
    - Fetch Gamma /markets?id=<market_id>
    - Extract outcomes[0], outcomes[1] as team_a_name, team_b_name
    - Inspect outcomePrices to infer winner_side ('A' or 'B') for closed markets
- Join this metadata back onto the time-series rows
- Output: valorant_markets_closed_enriched.csv with extra columns:
    team_a_name, team_b_name, winner_side, winner_team_name
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import json

import pandas as pd
import requests

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"


def gamma_get_markets_by_ids(ids: List[int]) -> List[dict]:
    """
    Fetch markets metadata for a list of numeric ids using Gamma /markets.
    """
    if not ids:
        return []

    url = f"{GAMMA_BASE_URL}/markets"
    # Gamma accepts repeated id params: id=1&id=2&...
    params: Dict[str, List[int]] = {"id": ids}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        return []
    return data


def infer_winner_from_outcome_prices(outcome_prices_raw) -> Optional[str]:
    """
    Infer winner_side ('A' or 'B') from outcomePrices.

    Strategy:
    - Parse outcomePrices into two floats.
    - If one is clearly greater than the other (diff >= 0.1), pick that side.
    - Otherwise, return None (ambiguous).
    """
    prices: List[float] = []
    if isinstance(outcome_prices_raw, str):
        try:
            # outcomePrices is often a JSON-encoded list string, e.g. '["0.81", "0.19"]'
            raw = outcome_prices_raw.strip()
            if raw.startswith("["):
                parsed = json.loads(raw)
                prices = [float(x) for x in parsed]
            else:
                prices = [float(x) for x in raw.split(",")]
        except Exception:
            prices = []
    elif isinstance(outcome_prices_raw, list):
        try:
            prices = [float(x) for x in outcome_prices_raw]
        except Exception:
            prices = []

    if len(prices) != 2:
        return None

    a, b = prices
    diff = abs(a - b)
    if diff < 0.1:
        # Too close to call confidently
        return None

    return "A" if a > b else "B"


def build_resolution_metadata_for_markets(
    market_ids: List[int],
) -> pd.DataFrame:
    """
    Build a metadata DataFrame with one row per market_id, including:
    - team_a_name
    - team_b_name
    - winner_side ('A'/'B'/None)
    - winner_team_name (if winner_side known)
    """
    rows: List[dict] = []

    # Chunk requests to avoid extremely long query strings
    batch_size = 50
    for i in range(0, len(market_ids), batch_size):
        batch = market_ids[i : i + batch_size]
        markets = gamma_get_markets_by_ids(batch)

        for m in markets:
            mid_raw = m.get("id")
            try:
                mid = int(mid_raw)
            except Exception:
                continue

            # Outcomes / team names
            outcomes_raw = m.get("shortOutcomes") or m.get("outcomes") or ""
            if isinstance(outcomes_raw, str):
                try:
                    # outcomes is often JSON-encoded list string
                    raw = outcomes_raw.strip()
                    if raw.startswith("["):
                        parsed = json.loads(raw)
                        outcomes = [str(x) for x in parsed]
                    else:
                        outcomes = [s.strip() for s in raw.split(",") if s.strip()]
                except Exception:
                    outcomes = []
            elif isinstance(outcomes_raw, list):
                outcomes = [str(s) for s in outcomes_raw]
            else:
                outcomes = []

            team_a_name = outcomes[0] if len(outcomes) > 0 else None
            team_b_name = outcomes[1] if len(outcomes) > 1 else None

            # Winner side
            outcome_prices_raw = m.get("outcomePrices") or ""
            winner_side = infer_winner_from_outcome_prices(outcome_prices_raw)

            if winner_side == "A":
                winner_team_name = team_a_name
            elif winner_side == "B":
                winner_team_name = team_b_name
            else:
                winner_team_name = None

            rows.append(
                {
                    "market_id": mid,
                    "team_a_name": team_a_name,
                    "team_b_name": team_b_name,
                    "winner_side": winner_side,
                    "winner_team_name": winner_team_name,
                }
            )

    return pd.DataFrame(rows)


def enrich_closed_csv_with_resolution(
    input_csv: str | Path,
    output_csv: str | Path,
) -> Path:
    """
    Read the closed Valorant time-series CSV, build resolution metadata per market,
    and write an enriched CSV with team names and winner_side.
    """
    input_path = Path(input_csv)
    df = pd.read_csv(input_path)

    # Ensure market_id is int for joining with Gamma ids
    df["market_id"] = df["market_id"].astype(int)
    unique_ids = sorted(df["market_id"].unique().tolist())

    meta_df = build_resolution_metadata_for_markets(unique_ids)
    if meta_df.empty:
        raise RuntimeError("No resolution metadata could be built for any market_id.")

    enriched = df.merge(meta_df, on="market_id", how="left")

    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(output_path, index=False)
    print(
        f"Wrote enriched CSV with resolution metadata to {output_path} "
        f"({len(enriched)} rows, {len(unique_ids)} markets)."
    )
    return output_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Enrich Valorant closed markets CSV with team names and winner_side "
            "using Gamma /markets metadata."
        )
    )
    parser.add_argument(
        "--input",
        type=str,
        default="Strategy 2/Threshold Calculation/Pulled Data/valorant_markets_closed.csv",
        help="Path to input closed-markets CSV.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="Strategy 2/Threshold Calculation/Pulled Data/valorant_markets_closed_enriched.csv",
        help="Path to output enriched CSV.",
    )
    args = parser.parse_args()

    enrich_closed_csv_with_resolution(
        input_csv=args.input,
        output_csv=args.output,
    )


