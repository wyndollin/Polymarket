"""
Valorant data pipeline: pull Polymarket Valorant markets and enrich with winners.

This file provides a single, configurable entrypoint for:
- Pulling a *single* Valorant match from its URL slug ("Data pull from URL" mode).
- Pulling *many* Valorant matches via the sports metadata (tag-based discovery).
- Optionally restricting to a date range (by gameStartTime / startDate).
- Optionally restricting to closed (resolved) markets only.
- Optionally enriching the dataset with team names and an inferred winner side.

You can control it either:
- Via CLI flags (see `main()`), or
- Via a JSON config file passed with `--config`, which can contain:
    {
      "mode": "sports",                // "sports" or "event"
      "event_slug": null,              // e.g. "val-rrq1-geng-2025-12-03" (mode="event")
      "start_date": "2025-01-01",      // "YYYY-MM-DD" or null
      "end_date": "2025-12-31",        // "YYYY-MM-DD" or null
      "closed_only": true,             // true = restrict to closed & enrich with winners
      "interval": "1m",                // e.g. "1m", "5m", "1h"
      "output": "Strategy 2/Threshold Calculation/Pulled Data/valorant_pipeline_range.csv"
    }

CLI flags always override values in the config file when both are provided.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import json

import pandas as pd
import requests
import yaml

from PullDataURL import (  # type: ignore
    ValorantMarket,
    _gamma_get,
    build_match_timeseries,
    run_data_pull,
)


GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
VALORANT_TAG_ID = 101672  # from /sports where sport == "valorant"


@dataclass
class PipelineParams:
    mode: str  # "event" or "sports"
    event_slug: Optional[str]
    start_date: Optional[str]  # "YYYY-MM-DD"
    end_date: Optional[str]  # "YYYY-MM-DD"
    closed_only: bool
    interval: str
    output: Path


# ---------- Date parsing / normalization ----------


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    return datetime.fromisoformat(date_str)


def _gamma_get_markets_by_ids(ids: List[int]) -> List[dict]:
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


def _filter_markets_by_date(
    market_ids: List[int],
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> List[int]:
    """
    Filter markets by their gameStartTime (preferred) or startDate.
    Only keep markets where start is within [start_dt, end_dt].
    """
    if start_dt is None and end_dt is None:
        return market_ids

    filtered: List[int] = []
    batch_size = 50
    for i in range(0, len(market_ids), batch_size):
        batch = market_ids[i : i + batch_size]
        markets = _gamma_get_markets_by_ids(batch)
        for m in markets:
            mid_raw = m.get("id")
            try:
                mid = int(mid_raw)
            except Exception:
                continue

            # Prefer gameStartTime; fallback to startDate
            start_ts = m.get("gameStartTime") or m.get("startDate")
            if not start_ts:
                continue

            try:
                # Gamma returns e.g. "2025-12-03 10:00:00+00" or ISO with Z.
                # Normalize to naive UTC for comparison with start_dt/end_dt.
                start = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                if start.tzinfo is not None:
                    start = start.replace(tzinfo=None)
            except Exception:
                continue

            if start_dt and start < start_dt:
                continue
            if end_dt and start > end_dt:
                continue

            filtered.append(mid)

    return filtered


# ---------- Valorant sports-tag discovery ----------


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
      GET /sports -> entry where sport == "valorant" -> tags includes VALORANT_TAG_ID.

    That tag_id corresponds to Valorant esports markets.
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

            # Try to infer winner index from outcomePrices (heuristic)
            final_winner_index: Optional[int] = None
            outcome_prices_raw = m.get("outcomePrices") or ""
            prices: List[float] = []
            if isinstance(outcome_prices_raw, str):
                try:
                    raw_prices = outcome_prices_raw.strip()
                    if raw_prices.startswith("["):
                        parsed = json.loads(raw_prices)
                        prices = [float(x) for x in parsed]
                    else:
                        prices = [float(x) for x in raw_prices.split(",")]
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
    dedup: Dict[str, ValorantMarket] = {}
    for m in markets:
        dedup[m.id] = m

    return list(dedup.values())


# ---------- Resolution enrichment (winners & team names) ----------


def _infer_winner_from_outcome_prices(outcome_prices_raw) -> Optional[str]:
    """
    Infer winner_side ('A' or 'B') from Gamma `outcomePrices`.

    Strategy:
    - Parse into two floats.
    - If one is clearly greater (diff >= 0.1), choose that side.
    - Otherwise, return None (ambiguous).
    """
    prices: List[float] = []
    if isinstance(outcome_prices_raw, str):
        try:
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
        return None

    return "A" if a > b else "B"


def _build_resolution_metadata_for_markets(market_ids: List[int]) -> pd.DataFrame:
    """
    Build a metadata table keyed by market_id with:
    - team_a_name
    - team_b_name
    - winner_side ('A'/'B'/None)
    - winner_team_name
    """
    rows: List[dict] = []
    batch_size = 50

    for i in range(0, len(market_ids), batch_size):
        batch = market_ids[i : i + batch_size]
        markets = _gamma_get_markets_by_ids(batch)

        for m in markets:
            mid_raw = m.get("id")
            try:
                mid = int(mid_raw)
            except Exception:
                continue

            outcomes_raw = m.get("shortOutcomes") or m.get("outcomes") or ""
            if isinstance(outcomes_raw, str):
                try:
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

            outcome_prices_raw = m.get("outcomePrices") or ""
            winner_side = _infer_winner_from_outcome_prices(outcome_prices_raw)

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
    Read a closed-markets CSV, build resolution metadata per market,
    and write an enriched CSV with team names and winner_side.
    """
    input_path = Path(input_csv)
    df = pd.read_csv(input_path)

    df["market_id"] = df["market_id"].astype(int)
    unique_ids = sorted(df["market_id"].unique().tolist())

    meta_df = _build_resolution_metadata_for_markets(unique_ids)
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


def run_event_mode(params: PipelineParams) -> Path:
    """
    Use the \"Data pull from URL\" flow (event slug) and optionally enrich.
    """
    if not params.event_slug:
        raise ValueError("event_slug is required when mode='event'.")

    # Step 1: raw pull by event slug into a CSV
    tmp_output = params.output
    print(f"Pulling event slug {params.event_slug} into {tmp_output}")
    run_data_pull(
        output_path=tmp_output,
        interval=params.interval,
        max_markets=None,
        search_term="valorant",
        event_slug=params.event_slug,
    )

    # Step 2: enrich if we care about winners (only meaningful for closed markets)
    if params.closed_only:
        enriched_output = params.output.with_name(
            params.output.stem + "_enriched" + params.output.suffix
        )
        enrich_closed_csv_with_resolution(
            input_csv=tmp_output,
            output_csv=enriched_output,
        )
        # Optionally treat the raw file as cache; keep for now.
        return enriched_output

    return tmp_output


def run_sports_mode(params: PipelineParams) -> Path:
    """
    Use the sports tag to discover many Valorant markets in a date range,
    then pull their price histories and optionally enrich.
    """
    # Step 1: discover all Valorant markets via sports tag
    print("Discovering Valorant markets via sports tag...")
    markets = discover_valorant_markets_by_tag(
        closed_only=params.closed_only,
    )
    if not markets:
        raise RuntimeError("No Valorant markets discovered via sports tag.")

    all_ids = sorted({int(m.id) for m in markets})

    # Step 2: filter by date range using gameStartTime/startDate
    start_dt = _parse_date(params.start_date)
    end_dt = _parse_date(params.end_date)
    if start_dt or end_dt:
        print(
            f"Filtering {len(all_ids)} markets to date range "
            f"{params.start_date} .. {params.end_date}"
        )
        filtered_ids = set(_filter_markets_by_date(all_ids, start_dt, end_dt))
        markets = [m for m in markets if int(m.id) in filtered_ids]

    if not markets:
        raise RuntimeError("No Valorant markets remain after date filtering.")

    print(f"Pulling price history for {len(markets)} markets...")

    all_rows: List[pd.DataFrame] = []
    for m in markets:
        ts_df = build_match_timeseries(market=m, interval=params.interval)
        if ts_df is not None and not ts_df.empty:
            all_rows.append(ts_df)

    if not all_rows:
        raise RuntimeError(
            "No historical time series built for any Valorant market "
            "discovered via sports tag."
        )

    full_df = pd.concat(all_rows, ignore_index=True)
    out = params.output
    out.parent.mkdir(parents=True, exist_ok=True)
    full_df.to_csv(out, index=False)
    print(f"Wrote {len(full_df)} rows across {len(markets)} markets to {out}")

    # Step 3: enrich if closed_only
    if params.closed_only:
        enriched_output = out.with_name(
            out.stem + "_enriched" + out.suffix
        )
        enrich_closed_csv_with_resolution(
            input_csv=out,
            output_csv=enriched_output,
        )
        # Optionally leave the raw CSV as cache.
        return enriched_output

    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Valorant data pipeline: pull Polymarket Valorant markets and "
            "optionally enrich with winners and team names."
        )
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["event", "sports"],
        required=False,
        help="event: pull single match by slug; sports: pull many via sports tag.",
    )
    parser.add_argument(
        "--event-slug",
        type=str,
        default=None,
        help="Polymarket event slug, e.g. 'val-rrq1-geng-2025-12-03' (mode=event).",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Filter sports-mode markets: earliest gameStartTime (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Filter sports-mode markets: latest gameStartTime (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--closed-only",
        action="store_true",
        help="If set, restrict to closed markets and enrich with winner_side.",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="1m",
        help="prices-history interval (e.g. 1m, 5m, 1h, 1d). Default: 1m",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="Strategy 2/Threshold Calculation/Pulled Data/valorant_pipeline_output.csv",
        help="Output CSV path for raw or enriched data.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Optional path to YAML config file (keys: mode, event_slug, start_date, end_date, "
             "closed_only, interval, output). CLI flags override config values.",
    )

    args = parser.parse_args()

    # Load config file (YAML) if provided
    cfg: dict = {}
    if args.config:
        cfg_path = Path(args.config)
        if not cfg_path.exists():
            raise FileNotFoundError(f"Config file not found: {cfg_path}")
        with cfg_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    def cfg_or(name: str, default):
        return cfg.get(name, default)

    # Build PipelineParams, letting CLI flags override config entries.
    mode = args.mode or cfg_or("mode", None)
    if mode is None:
        raise ValueError("You must specify mode via --mode or in the config file.")

    params = PipelineParams(
        mode=mode,
        event_slug=args.event_slug or cfg_or("event_slug", None),
        start_date=args.start_date or cfg_or("start_date", None),
        end_date=args.end_date or cfg_or("end_date", None),
        closed_only=bool(
            args.closed_only
            or cfg_or("closed_only", False)
        ),
        interval=args.interval or cfg_or("interval", "1m"),
        output=Path(args.output or cfg_or("output", "Strategy 2/Threshold Calculation/Pulled Data/valorant_pipeline_output.csv")),
    )

    if params.mode == "event":
        final_path = run_event_mode(params)
    else:
        final_path = run_sports_mode(params)

    print(f"Pipeline completed. Final output at: {final_path}")


if __name__ == "__main__":
    main()

