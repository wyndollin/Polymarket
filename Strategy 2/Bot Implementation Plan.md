# Valorant Straddle Bot: Implementation Plan

This document outlines a comprehensive plan to build an automated trading bot that executes the Valorant volatility straddle strategy with the validated multi-threshold exit approach.

---

## 1. System Architecture Overview

The bot will consist of several interconnected components:

```
┌─────────────────┐
│  Market Scanner │  → Identifies qualifying markets
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Order Builder  │  → Constructs entry orders (both sides)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Execution Engine│  → Executes orders, monitors fills
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Orderbook Engine│  → Tracks prices, detects threshold crossings
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Strategy Engine │  → Decides when to enter/exit based on thresholds
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Risk Manager   │  → Position sizing, exposure limits, stop-losses
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Persistence    │  → Logs trades, stores state, enables recovery
└─────────────────┘
```

---

## 2. Component Specifications

### 2.1. Market Scanner

**Purpose**: Identify Valorant markets that meet entry criteria.

**Requirements**:
- Filter markets by:
  - Sport: Valorant
  - Market type: Match winner (YES/NO)
  - Status: Active/live
  - Both sides priced near 0.5 (±0.05 tolerance)
- Poll exchange API at configurable intervals (e.g., every 5-10 seconds).
- Maintain a list of active positions to avoid duplicate entries.

**Inputs**:
- Exchange API connection
- Configuration: price tolerance, polling interval, market filters

**Outputs**:
- List of qualifying market IDs
- Current prices for both sides

**Implementation Notes**:
- Use exchange-specific market filtering (e.g., Polymarket GraphQL API).
- Cache market metadata to reduce API calls.
- Handle API rate limits gracefully.

---

### 2.2. Order Builder

**Purpose**: Construct entry orders for the straddle position.

**Requirements**:
- Calculate position size based on:
  - Available capital
  - Risk parameters (max % of bankroll per trade)
  - Current bankroll
- Create two orders:
  - Buy YES at current price (or limit order slightly above)
  - Buy NO at current price (or limit order slightly above)
- Ensure orders are atomic (both must execute or neither).

**Inputs**:
- Market ID
- Current prices (YES, NO)
- Bankroll amount
- Risk parameters

**Outputs**:
- Two order objects (YES order, NO order)
- Total cost calculation

**Implementation Notes**:
- Consider using exchange-specific order types (market vs. limit).
- Account for fees in position sizing calculations.
- Validate that both sides sum to ~1.0 (accounting for spread).

---

### 2.3. Execution Engine

**Purpose**: Execute orders and monitor their status.

**Requirements**:
- Submit orders to exchange API.
- Monitor order status (pending, filled, cancelled, rejected).
- Handle partial fills gracefully.
- Retry failed orders with exponential backoff.
- Cancel orders if one side fails to fill within timeout window.

**Inputs**:
- Order objects from Order Builder
- Exchange API credentials
- Timeout parameters

**Outputs**:
- Fill confirmations
- Order status updates
- Error notifications

**Implementation Notes**:
- Implement idempotency keys to prevent duplicate orders.
- Log all order submissions and fills for audit trail.
- Handle exchange-specific error codes and retry logic.

---

### 2.4. Orderbook Engine

**Purpose**: Monitor live prices and detect threshold crossings.

**Requirements**:
- Subscribe to or poll orderbook/price feeds for active positions.
- Track current prices for both sides of each active position.
- Identify the "cheap side" (lower price) and "favorite" (higher price).
- Detect when cheap side crosses threshold levels:
  - 19% (0.19)
  - 18% (0.18)
  - 17% (0.17)
- Track which thresholds have already been crossed (to avoid duplicate exits).

**Inputs**:
- Active position IDs
- Exchange price feed (WebSocket or polling)
- Threshold configuration

**Outputs**:
- Price updates per position
- Threshold crossing events
- Current position state (cheap side price, favorite side price)

**Implementation Notes**:
- Use WebSocket subscriptions if available for real-time updates.
- Fall back to polling if WebSocket is unavailable.
- Handle price feed disconnections gracefully (reconnect logic).
- Account for bid/ask spread when determining execution prices.

---

### 2.5. Strategy Engine

**Purpose**: Make entry/exit decisions based on strategy rules.

**Requirements**:
- **Entry Logic**:
  - Trigger when market scanner finds qualifying market.
  - Verify both sides are still near 0.5.
  - Check risk manager approval.
  - Signal order builder to create entry orders.

- **Exit Logic** (Multi-Threshold):
  - When cheap side crosses 19%:
    - Sell 33% of cheap side position.
    - Mark threshold 19% as "hit".
  - When cheap side crosses 18%:
    - Sell 33% of remaining cheap side position.
    - Mark threshold 18% as "hit".
  - When cheap side crosses 17%:
    - Sell remaining 34% of cheap side position.
    - Mark threshold 17% as "hit".
  - Hold favorite side to resolution (or optional early exit if price becomes favorable).

**Inputs**:
- Market scanner events
- Orderbook threshold crossings
- Risk manager status
- Current position state

**Outputs**:
- Entry signals
- Exit signals (with allocation percentages)
- Position state updates

**Implementation Notes**:
- Maintain state machine for each position:
  - `WAITING_ENTRY` → `ENTERED` → `EXITED_19` → `EXITED_18` → `EXITED_17` → `RESOLVED`
- Handle edge cases:
  - Price jumps directly from 20% to 16% (execute all exits immediately).
  - Price rebounds above threshold (don't re-enter, but track for potential early exit of favorite).
- Implement configurable thresholds (allow adjustment without code changes).

---

### 2.6. Risk Manager

**Purpose**: Enforce position sizing, exposure limits, and risk controls.

**Requirements**:
- **Position Sizing**:
  - Calculate max position size per trade (e.g., 2-5% of bankroll).
  - Account for fees and slippage in sizing.
  - Ensure sufficient capital for all active positions.

- **Exposure Limits**:
  - Maximum number of concurrent positions (e.g., 5-10).
  - Maximum total exposure as % of bankroll (e.g., 20-30%).
  - Per-market exposure limits.

- **Stop-Loss / Safety Controls**:
  - Optional: Exit all positions if bankroll drops below threshold.
  - Optional: Pause trading if drawdown exceeds limit.
  - Monitor for unusual market conditions (suspended markets, extreme spreads).

**Inputs**:
- Current bankroll
- Active positions
- Proposed position size
- Risk parameters (from config)

**Outputs**:
- Approved/rejected entry requests
- Position size adjustments
- Risk alerts

**Implementation Notes**:
- Implement conservative defaults (can be adjusted based on backtest results).
- Log all risk decisions for analysis.
- Support "dry run" mode where risk manager approves but no real orders are placed.

---

### 2.7. Persistence Layer

**Purpose**: Store trade history, position state, and enable recovery.

**Requirements**:
- **Trade Logging**:
  - Log all entries, exits, and fills.
  - Store timestamps, prices, sizes, fees.
  - Track P/L per trade and cumulative.

- **State Persistence**:
  - Save active position state (market ID, entry prices, exit thresholds hit).
  - Enable bot recovery after crashes (reload active positions).
  - Store configuration snapshots.

- **Analytics**:
  - Track performance metrics:
    - Win rate
    - Average P/L per trade
    - Drawdowns
    - Threshold hit rates
  - Generate periodic reports (daily, weekly).

**Inputs**:
- All trade events
- Position state changes
- Configuration updates

**Outputs**:
- Database records
- Analytics reports
- Recovery state files

**Implementation Notes**:
- Use SQLite for simplicity (can migrate to PostgreSQL if needed).
- Schema:
  - `trades` table: entry/exit records
  - `positions` table: active position state
  - `config` table: configuration history
- Implement periodic backups.

---

## 3. Technical Stack Recommendations

### 3.1. Programming Language
- **Python 3.10+**: Rich ecosystem, good for data analysis and API integration.

### 3.2. Core Libraries
- **Exchange API**: Polymarket SDK or direct GraphQL/HTTP client.
- **Async Framework**: `asyncio` + `aiohttp` for concurrent API calls.
- **Database**: `sqlite3` or `sqlalchemy` for persistence.
- **Configuration**: `pydantic` + `pyyaml` for config management.
- **Logging**: `logging` module with file rotation.
- **Testing**: `pytest` + `pytest-asyncio`.

### 3.3. Infrastructure
- **Deployment**: Docker container for portability.
- **Monitoring**: Log aggregation (optional: Sentry for error tracking).
- **Scheduling**: Bot runs continuously (or via systemd/cron if polling-based).

---

## 4. Implementation Phases

### Phase 1: Core Infrastructure (Week 1-2)
- [ ] Set up project structure and dependencies.
- [ ] Implement configuration management.
- [ ] Set up logging and error handling.
- [ ] Create database schema and persistence layer.
- [ ] Implement basic exchange API client (read-only initially).

**Deliverable**: Bot skeleton that can connect to exchange and log data.

---

### Phase 2: Market Scanner & Orderbook Engine (Week 2-3)
- [ ] Implement market scanner with filtering logic.
- [ ] Implement orderbook engine with price tracking.
- [ ] Add WebSocket support (or polling fallback).
- [ ] Test price feed reliability and reconnection logic.

**Deliverable**: Bot can identify qualifying markets and track prices in real-time.

---

### Phase 3: Order Building & Execution (Week 3-4)
- [ ] Implement order builder with position sizing.
- [ ] Implement execution engine with order submission.
- [ ] Add fill monitoring and status tracking.
- [ ] Test atomic order execution (both sides).

**Deliverable**: Bot can enter straddle positions automatically.

---

### Phase 4: Strategy Engine & Multi-Threshold Exits (Week 4-5)
- [ ] Implement strategy engine with entry/exit logic.
- [ ] Add multi-threshold exit logic (19%, 18%, 17%).
- [ ] Implement position state machine.
- [ ] Handle edge cases (price jumps, rebounds).

**Deliverable**: Bot can execute full strategy cycle (entry → graduated exits → resolution).

---

### Phase 5: Risk Management (Week 5-6)
- [ ] Implement risk manager with position sizing.
- [ ] Add exposure limits and safety controls.
- [ ] Integrate risk checks into entry/exit flow.
- [ ] Add dry-run mode for testing.

**Deliverable**: Bot enforces risk limits and can operate safely.

---

### Phase 6: Testing & Validation (Week 6-7)
- [ ] Write unit tests for all components.
- [ ] Run extended dry-run tests on live markets (no real orders).
- [ ] Backtest on historical data (if available).
- [ ] Test recovery after crashes.
- [ ] Performance testing (latency, throughput).

**Deliverable**: Bot is tested and validated before live trading.

---

### Phase 7: Production Deployment (Week 7-8)
- [ ] Set up production environment (VPS, monitoring).
- [ ] Deploy with minimal position sizes.
- [ ] Monitor closely for first week.
- [ ] Gradually increase position sizes as confidence grows.
- [ ] Set up alerts and monitoring dashboards.

**Deliverable**: Bot running live with real capital (initially small).

---

## 5. Configuration Schema

```yaml
# config.yaml

exchange:
  api_key: "${EXCHANGE_API_KEY}"
  api_secret: "${EXCHANGE_API_SECRET}"
  base_url: "https://api.polymarket.com"
  websocket_url: "wss://clob.polymarket.com"
  rate_limit_delay: 0.1  # seconds between API calls

strategy:
  entry:
    price_tolerance: 0.05  # Both sides must be within 0.45-0.55
    min_market_age: 300  # seconds (avoid entering too early)
  
  exit:
    thresholds:
      - level: 0.19
        allocation: 0.33  # Sell 33% at 19%
      - level: 0.18
        allocation: 0.33  # Sell 33% at 18%
      - level: 0.17
        allocation: 0.34  # Sell remaining 34% at 17%
    
    favorite_exit:
      enabled: false  # Hold to resolution by default
      early_exit_price: 0.95  # Optional: exit favorite if it reaches 95%

risk:
  position_sizing:
    max_position_pct: 0.03  # 3% of bankroll per trade
    min_position_size: 10  # USD minimum
    max_position_size: 100  # USD maximum
  
  exposure:
    max_concurrent_positions: 5
    max_total_exposure_pct: 0.20  # 20% of bankroll
  
  safety:
    stop_loss_pct: 0.20  # Pause if drawdown > 20%
    min_bankroll: 100  # USD minimum to continue trading

database:
  path: "data/bot.db"
  backup_interval: 3600  # seconds

logging:
  level: "INFO"
  file: "logs/bot.log"
  max_bytes: 10485760  # 10MB
  backup_count: 5

monitoring:
  polling_interval: 5  # seconds for market scanner
  price_update_interval: 1  # seconds for orderbook engine
  health_check_interval: 60  # seconds
```

---

## 6. Error Handling & Edge Cases

### 6.1. Exchange API Failures
- **Symptom**: API timeout or connection error.
- **Handling**: Retry with exponential backoff, log error, continue monitoring other positions.
- **Recovery**: Reconnect and resume normal operation.

### 6.2. Partial Fills
- **Symptom**: Only one side of straddle fills, other side remains pending.
- **Handling**: Cancel unfilled side if timeout exceeded, log partial fill, adjust position tracking.

### 6.3. Price Feed Disconnection
- **Symptom**: WebSocket disconnects, prices stop updating.
- **Handling**: Fall back to polling, attempt WebSocket reconnect, alert operator.

### 6.4. Market Suspension
- **Symptom**: Market becomes inactive or suspended mid-trade.
- **Handling**: Hold position, monitor for resolution, log event.

### 6.5. Rapid Price Movements
- **Symptom**: Price jumps directly from 20% to 16%, skipping thresholds.
- **Handling**: Execute all remaining exits immediately at current price.

### 6.6. Price Rebound
- **Symptom**: Cheap side rebounds above threshold after exit.
- **Handling**: Don't re-enter (already exited), but track for potential early exit of favorite if it becomes cheap.

---

## 7. Monitoring & Alerts

### 7.1. Key Metrics to Track
- **Performance**:
  - Total P/L (daily, weekly, monthly)
  - Win rate
  - Average profit per trade
  - Maximum drawdown
  
- **Operational**:
  - Number of active positions
  - API error rate
  - Price feed uptime
  - Order fill rate

### 7.2. Alerts
- **Critical** (immediate action required):
  - Exchange API failure (no response for > 5 minutes)
  - Unfilled orders stuck > 10 minutes
  - Bankroll below minimum threshold
  
- **Warning** (investigate soon):
  - Drawdown exceeds 15%
  - Multiple consecutive losing trades (> 5)
  - Price feed disconnection

### 7.3. Reporting
- **Daily Report**:
  - Trades executed
  - P/L summary
  - Active positions
  - Risk metrics
  
- **Weekly Report**:
  - Performance vs. backtest expectations
  - Threshold hit rates
  - Recommendations for parameter adjustments

---

## 8. Testing Strategy

### 8.1. Unit Tests
- Test each component in isolation.
- Mock exchange API responses.
- Verify edge case handling.

### 8.2. Integration Tests
- Test component interactions.
- Use testnet/sandbox exchange if available.
- Verify end-to-end flow (entry → exits → resolution).

### 8.3. Dry-Run Testing
- Run bot on live markets with `dry_run: true`.
- Verify all logic without placing real orders.
- Monitor for 1-2 weeks before going live.

### 8.4. Paper Trading
- If exchange supports paper trading, use it.
- Track performance vs. backtest expectations.
- Validate execution assumptions (slippage, fees).

---

## 9. Security Considerations

### 9.1. API Credentials
- Store credentials in environment variables (never in code).
- Use read-only API keys when possible for testing.
- Rotate credentials periodically.

### 9.2. Code Security
- Review all external dependencies for vulnerabilities.
- Implement input validation for all user inputs.
- Use HTTPS for all API communications.

### 9.3. Operational Security
- Run bot on isolated VPS (not personal machine).
- Enable firewall rules (only necessary ports).
- Regular backups of database and configuration.
- Monitor for unauthorized access.

---

## 10. Post-Launch Optimization

### 10.1. Parameter Tuning
- Monitor threshold hit rates vs. expectations.
- Adjust allocation percentages if needed.
- Fine-tune position sizing based on volatility.

### 10.2. Strategy Refinements
- Test context-aware thresholds (map, round range).
- Experiment with early exit of favorite side.
- Consider adding filters (tournament tier, team ratings).

### 10.3. Performance Analysis
- Compare live results to backtest.
- Identify sources of deviation (slippage, fees, execution delays).
- Optimize based on real-world data.

---

## 11. Success Criteria

The bot is considered successful if:

1. **Profitability**: Positive expected value over 100+ trades.
2. **Reliability**: > 99% uptime, no critical failures.
3. **Risk Management**: No single trade loses > 5% of bankroll.
4. **Execution**: > 95% of intended orders fill successfully.
5. **Performance**: Matches or exceeds backtest expectations (accounting for fees/slippage).

---

## 12. Next Steps

1. **Review this plan** and adjust based on exchange-specific requirements.
2. **Set up development environment** (Python, dependencies, exchange API access).
3. **Begin Phase 1** implementation (core infrastructure).
4. **Iterate** through phases, testing thoroughly at each step.
5. **Deploy** with small position sizes and scale gradually.

---

## Appendix: Exchange-Specific Notes

### Polymarket Considerations
- Uses GraphQL API for market data.
- WebSocket available for real-time price updates.
- Order execution via CLOB (Central Limit Order Book).
- Fees: ~2% on trades (factor into EV calculations).
- Market resolution can take time after match ends.

### Alternative Exchanges
- If using different exchange, adapt API client accordingly.
- Verify fee structure and execution model.
- Test order types and fill guarantees.

---

**Document Version**: 1.0  
**Last Updated**: [Current Date]  
**Status**: Ready for Implementation

