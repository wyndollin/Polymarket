# Polymarket Passive Arbitrage / Micro MM Bot

This repo implements a **passive arbitrage / micro market-making agent** for **Polymarket**. The bot scans CLOB markets for persistent \(> X\) cent spreads between the best bid and best ask, places resting limit orders on the side(s) most likely to fill, and then closes positions by taking the opposite side when a profitable cross appears.

## High-level strategy

- **What**: Continuously monitor Polymarket CLOB markets, look for sufficiently wide and liquid spreads, place small limit orders, and exit via opposing trades when profit after fees is locked in.
- **How**:
  - Ingest **Gamma API** market metadata and **CLOB** orderbook data (REST + WebSocket).
  - Maintain in-memory orderbooks per candidate market.
  - Use a strategy engine to decide: *whether* to trade, *which side*, *what size*, *what price*, and *for how long* (TTL).
  - Build and sign CLOB orders using the official client libraries.
  - Execute orders, handle fills, and manage risk/inventory limits.
  - Persist all activity and support backtesting/simulation.
- **Strengths**:
  - Low capital per trade, frequent small wins, simple "buy low, sell slightly higher" logic.
  - Uses on-chain custody + authenticated API, so execution is auditable.
  - Works best on moderately liquid markets with stale human liquidity.
- **Weaknesses / risks**:
  - Latency/API delays can make small spreads disappear; bots compete on speed.
  - Maker/taker fees, settlement costs, and token allowance friction reduce edge.
  - Inventory risk if markets move strongly or liquidity vanishes.
  - Rate limits, auth complexity, and potential front-running by faster actors.

For more detailed docs on the underlying platform, see:

- **Polymarket developer overview**: [https://docs.polymarket.com/developers](https://docs.polymarket.com/developers)
- **Gamma-Markets (public market data)**: [https://gamma-api.polymarket.com](https://gamma-api.polymarket.com)
- **Gamma API reference (markets/events)**: [https://docs.polymarket.com/api-reference/markets/get-market-by-id](https://docs.polymarket.com/api-reference/markets/get-market-by-id)
- **CLOB API docs**: [https://docs.polymarket.com/developers/CLOB/introduction](https://docs.polymarket.com/developers/CLOB/introduction)
- **Data-API (historical trades/activity)**: [https://data-api.polymarket.com/](https://data-api.polymarket.com/)

## System architecture

The bot is organized into the following high-level components:

1. **Market Scanner (Fetcher)**
   - Continuously fetches candidate markets and market metadata (volume, expiry, tags).
   - **Inputs**: Gamma API `GET /markets`, `GET /events` (paginated).
   - **Output**: candidate market list passed to the Orderbook Engine.
   - **Poll cadence**: e.g., 1–5s for active lists; slower for low-activity.

2. **Orderbook Engine (Real-time layer)**
   - Maintains a near-real-time in-memory orderbook per candidate market.
   - **Sources**: CLOB WebSocket `wss://ws-subscriptions-clob.polymarket.com/ws/` (orderbook deltas), plus CLOB REST snapshots.
   - Computes best bid/ask, aggregated depth, and detects spreads / trade ticks.

3. **Strategy Engine (Decision logic)**
   - Decides whether to place an order, and if so: side, price, size, and TTL.
   - **Inputs**: orderbook snapshot, market metadata, risk settings, fee model, latency stats.
   - **Output**: order intents (BUY/SELL, market_id, price, size, TTL, attribution headers).

4. **Order Builder & Signer**
   - Builds limit order payloads expected by the CLOB and signs them.
   - Uses official client libraries (`py-clob-client` or `polymarket/clob-client`).
   - Attaches L2 headers: `POLY_ADDRESS`, `POLY_SIGNATURE`, `POLY_TIMESTAMP`, `POLY_API_KEY`, `POLY_PASSPHRASE`.

5. **Execution Engine (CLOB client)**
   - Submits orders via CLOB REST (single or batch), manages cancellations, queries status.
   - Behavior: optimistic placement, track via websockets for fills, respect rate limits.
   - Includes retry logic with exponential backoff and idempotency.

6. **Fill Handler & Exit Logic**
   - Reacts to partial/full fills from websockets or Data-API.
   - Computes realized/unrealized PnL and decides on exit (marketable vs. limit).

7. **Risk / Inventory Manager**
   - Enforces exposure limits, daily loss limits, and forced unwind rules.
   - Cancels orders or forces market exits when limits are breached or expiry nears.

8. **Persistence & Telemetry (DB + Metrics)**
   - Stores orders, fills, market snapshots, and PnL.
   - Exposes metrics/dashboards for health and performance.

9. **Backtest & Simulation Module**
   - Replays historical trade/orderbook data via Data-API.
   - Outputs expected winrate, average returns, and drawdowns for parameter sets.

10. **Operator UI / CLI**
   - Lets an operator view open orders, cancel, adjust risk params, and inspect PnL.

## Project layout

Planned high-level layout (language-agnostic skeleton):

- `bot/`
  - `market_scanner/`
  - `orderbook_engine/`
  - `strategy_engine/`
  - `order_builder/`
  - `execution_engine/`
  - `fills/`
  - `risk/`
  - `persistence/`
  - `backtest/`
  - `cli/`
- `infra/` — deployment configs, monitoring, and ops tooling.

This structure is just a starting point and can be adapted as we choose a primary implementation language and frameworks.

## Requirements / resources

- Polygon wallet(s) with MATIC + relevant stable tokens.
- Polymarket CLOB API credentials (L1 and L2 headers, plus signing key).
- HTTP + WebSocket clients, and the official CLOB client library.
- Low-latency compute, orderbook cache, database, and monitoring/alerting.

See `.cursor/rules` for a more detailed strategy description and operational checklist.
