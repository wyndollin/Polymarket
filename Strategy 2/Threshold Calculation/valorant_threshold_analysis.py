"""
Offline analysis tools for the Valorant volatility straddle.

Goal:
- Load historical Valorant market snapshots.
- Estimate q(p_c) = P(favorite wins | cheap side at price p_c).
- Compute EV(q, p_c) and identify candidate exit thresholds p*.

This module is intentionally standalone and offline: it does NOT
connect to any APIs or run a bot. You just point it at a CSV/Parquet
export of historical markets.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Optional, Tuple

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import proportion_confint


@dataclass
class ThresholdSummary:
    """Summary statistics for a single cheap-side price bin."""

    bin_level: float
    hits: int
    wins: int
    q_hat: float
    ci_low: float
    ci_high: float
    required_q: float
    ev_estimate: float


def load_snapshots(path: str | Path) -> pd.DataFrame:
    """
    Load historical market snapshots.

    Expected minimal columns (you can add more):
    - market_id: unique identifier per match/market
    - ts: timestamp (anything sortable; string or datetime)
    - price_team_a, price_team_b: YES prices or implied win probabilities
    - final_winner: "A" or "B" (or 0/1 for favorite wins; see below)

    You can adapt this to your real export schema.
    """
    path = Path(path)
    if path.suffix in {".parquet", ".pq"}:
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    # Basic sanity checks / renames can go here if needed.
    return df


def prepare_favorite_view(
    df: pd.DataFrame,
    winner_col: str = "final_winner",
    price_a_col: str = "price_team_a",
    price_b_col: str = "price_team_b",
) -> pd.DataFrame:
    """
    Transform raw snapshot data into a "favorite vs cheap" view.

    Returns a DataFrame with at least:
    - market_id
    - ts
    - price_fav
    - price_cheap
    - final_fav_won (0/1)

    Assumes `final_winner` is "A"/"B" or 0/1; adapt as needed.
    """
    df = df.copy()

    # Determine favorite and cheap side at each snapshot
    fav_is_a = df[price_a_col] >= df[price_b_col]
    df["price_fav"] = np.where(fav_is_a, df[price_a_col], df[price_b_col])
    df["price_cheap"] = np.where(fav_is_a, df[price_b_col], df[price_a_col])

    # Map final_winner to "fav won?" boolean
    final = df[[ "market_id", winner_col ]].drop_duplicates("market_id")

    def _fav_won(row: pd.Series) -> int:
        w = row[winner_col]
        if isinstance(w, str):
            if w.upper() == "A":
                return int(row["fav_side"] == "A")
            if w.upper() == "B":
                return int(row["fav_side"] == "B")
        # If already 0/1 as "team A wins", treat favorite==A as 1 etc.
        # You may customize this mapping to your actual schema.
        return int(bool(w))

    # Side of favorite at market level (using last snapshot as proxy)
    latest = (
        df.sort_values("ts")
        .groupby("market_id")
        .tail(1)[["market_id", price_a_col, price_b_col]]
    )
    latest["fav_side"] = np.where(
        latest[price_a_col] >= latest[price_b_col],
        "A",
        "B",
    )

    merged = final.merge(latest[["market_id", "fav_side"]], on="market_id", how="left")
    merged["final_fav_won"] = merged.apply(_fav_won, axis=1)

    df = df.merge(merged[["market_id", "final_fav_won"]], on="market_id", how="left")
    return df


def build_hit_events(
    df: pd.DataFrame,
    bins: Iterable[float],
    ts_col: str = "ts",
) -> pd.DataFrame:
    """
    For each market and each cheap-side bin, record the first time
    the cheap price goes below or equal to that bin.

    Returns a DataFrame with one row per (market_id, bin) event:
    - market_id
    - bin
    - price_at_hit
    - final_fav_won
    """
    records: list[dict] = []
    bins_arr = np.array(sorted(bins))

    for mid, g in df.groupby("market_id"):
        g = g.sort_values(ts_col)
        final_flag = int(g["final_fav_won"].iloc[-1])

        for b in bins_arr:
            hits = g[g["price_cheap"] <= b]
            if hits.empty:
                continue
            first_hit = hits.iloc[0]
            records.append(
                {
                    "market_id": mid,
                    "bin": float(b),
                    "price_at_hit": float(first_hit["price_cheap"]),
                    "final_fav_won": final_flag,
                }
            )

    return pd.DataFrame.from_records(records)


def summarize_bins(
    events: pd.DataFrame,
    cost_buffer: float = 0.02,
) -> pd.DataFrame:
    """
    Aggregate hit events per bin and compute:
    - hits, wins
    - q_hat and Wilson confidence interval
    - required_q for EV > 0 given cost_buffer
    - ev_estimate using q_hat
    """
    if events.empty:
        return pd.DataFrame(
            columns=[
                "bin",
                "hits",
                "wins",
                "q_hat",
                "ci_low",
                "ci_high",
                "required_q",
                "ev_estimate",
            ]
        )

    summary = (
        events.groupby("bin")
        .agg(
            hits=("market_id", "count"),
            wins=("final_fav_won", "sum"),
        )
        .reset_index()
    )

    summary["q_hat"] = summary["wins"] / summary["hits"]

    ci = summary.apply(
        lambda r: proportion_confint(
            count=int(r["wins"]),
            nobs=int(r["hits"]),
            alpha=0.05,
            method="wilson",
        ),
        axis=1,
        result_type="expand",
    )
    summary["ci_low"] = ci[0]
    summary["ci_high"] = ci[1]

    summary["required_q"] = 1.0 - summary["bin"] + cost_buffer
    summary["ev_estimate"] = summary["q_hat"] + summary["bin"] - 1.0 - cost_buffer

    return summary.sort_values("bin").reset_index(drop=True)


def find_candidate_thresholds(
    summary: pd.DataFrame,
    min_hits: int = 100,
) -> pd.DataFrame:
    """
    Filter bins to those that:
    - have at least `min_hits` samples, and
    - lower CI bound is above required_q (conservative EV > 0).
    """
    if summary.empty:
        return summary

    mask = (summary["hits"] >= min_hits) & (summary["ci_low"] > summary["required_q"])
    return summary[mask].copy()


def run_threshold_study(
    snapshots_path: str | Path,
    bins: Optional[Iterable[float]] = None,
    cost_buffer: float = 0.02,
    min_hits: int = 100,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    High-level convenience function:

    1. Load snapshots.
    2. Prepare favorite/cheap view.
    3. Build hit events.
    4. Summarize bins and compute EV.
    5. Return (full_summary, candidate_thresholds).
    """
    if bins is None:
        bins = np.arange(0.05, 0.51, 0.05)

    df = load_snapshots(snapshots_path)
    df = prepare_favorite_view(df)

    events = build_hit_events(df, bins=bins)
    summary = summarize_bins(events, cost_buffer=cost_buffer)
    candidates = find_candidate_thresholds(summary, min_hits=min_hits)
    return summary, candidates


if __name__ == "__main__":
    # Example usage (you can run this manually from the CLI):
    #
    #   python valorant_threshold_analysis.py /path/to/valorant_markets.csv
    #
    import argparse

    parser = argparse.ArgumentParser(
        description="Offline Valorant exit-threshold study (no trading)."
    )
    parser.add_argument(
        "snapshots_path",
        type=str,
        help="Path to CSV/Parquet with historical Valorant market snapshots.",
    )
    parser.add_argument(
        "--cost-buffer",
        type=float,
        default=0.02,
        help="Cost/safety buffer c in EV condition q > 1 - p_c + c (default: 0.02).",
    )
    parser.add_argument(
        "--min-hits",
        type=int,
        default=100,
        help="Minimum number of events per bin to consider it as a candidate threshold.",
    )

    args = parser.parse_args()

    full_summary, candidates = run_threshold_study(
        snapshots_path=args.snapshots_path,
        cost_buffer=args.cost_buffer,
        min_hits=args.min_hits,
    )

    print("=== Bin summary ===")
    print(full_summary.to_string(index=False))
    print("\n=== Candidate thresholds (conservative EV > 0) ===")
    print(candidates.to_string(index=False))


