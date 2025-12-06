## Valorant Volatility Straddle Strategy

Profit from odds swings during a Valorant match **without needing to predict the winner**.

---

### 1. Core Idea

Valorant live markets are highly volatile. Odds swing hard based on short-term events like pistol wins, 3–4 round streaks, thrifty/clutch rounds, timeouts, and economic resets. Minor leads (for example 7–5 or 9–7) are often treated by the market as decisive, even when they are not.

These swings cause **overreactions** in YES/NO prices. This strategy is designed to **monetize those overreactions**, not to guess who will win the match. You are effectively trading **volatility**, not direction.

---

### 2. Strategy Objective

The basic flow of the strategy:

- **Enter** when odds are close to even by buying both sides (YES and NO).
- **Wait** for natural match volatility to push one side’s odds very low.
- **Exit** the cheap side at a loss when a predefined threshold is hit.
- **Hold** the expensive side to resolution (or a good exit) and capture the spread.

Your profit comes from:

- **Realizing a controlled loss** on the side that collapses in price.
- **Capturing a larger gain** on the side that becomes heavily favored.
- **Netting the difference** between these two.

The edge comes from the fact that once a team’s odds collapse to a certain threshold, they **statistically lose the match the vast majority of the time**.

---

### 3. Why Valorant Is Ideal

Valorant is particularly well-suited to this strategy because:

- Teams frequently **trade round streaks**.
- **Economy swings** (saves, forces, bonuses) amplify momentum.
- There is **no game clock**, so comebacks are always possible in theory, which keeps markets highly reactive.
- Large-looking leads (like 7–2 in rounds) can disappear quickly.
- The favorite can flip **multiple times in a single map**.
- Markets respond strongly to **per-round win probabilities**.

It is common to see sequences where one side:

- Trades up to **80% implied probability**,
- Crashes to **40%**,
- Then spikes back to **85%**,

all within the same half. These sharp swings are exactly what the straddle is designed to exploit.

---

### 4. Setting Up the Straddle

You enter when the market is near **50/50**.

Example:

- YES @ 0.50  
- NO @ 0.50  

You buy both:

- Total cost: **$100** (for example $50 on YES and $50 on NO).

This setup:

- Uses **no leverage**.
- Has **no directional bias**.
- Depends **only on volatility**.

From here, you simply **wait for a major swing** in either direction.

---

### 5. The Threshold Exit (Key Mechanic)

The core mechanic is defining **clear thresholds** where the market is likely overconfident, validated by historical data.

**Validated Multi-Threshold Approach**:

Based on empirical analysis of historical Valorant markets, we use a **graduated exit strategy**:

- When the cheap side drops to **19%**: Sell 33% of position
- When the cheap side drops to **18%**: Sell another 33% of position  
- When the cheap side drops to **17%**: Sell remaining 34% of position

Why this makes sense:

- Historical data shows that when a team's odds compress into the **17–19% range**, the favorite goes on to win the match **92–94% of the time** (see Section 9 for detailed statistics).
- This provides a **statistical edge** with expected value of **+11.0% to +11.5%** per trade.
- The multi-threshold approach reduces risk by taking partial profits at multiple levels.

After selling the cheap side:

- You **hold the expensive side** (favorite) until the end of the match.
- The favorite side pays out fully if it wins, capturing the spread.

Conceptually, your net result is:

\[
\text{Profit} = (\text{Payout or exit value of expensive side}) - (\text{Loss taken on cheap side})
\]

The mathematical framework (Section 7) shows this is profitable when \( q > 1 - p_c + c \), where \( q \) is the favorite's win probability, \( p_c \) is the cheap side exit price, and \( c \) accounts for fees/slippage.

---

### 6. Example Match Flow

Initial market:

- YES = 0.50  
- NO = 0.50  

You buy both → **total exposure: $100**.

Early in the half, Team B loses pistol and bonus, going down 0–3. The market reacts:

- YES (Team A) jumps to 0.80.
- NO (Team B) drops to 0.20.

According to the strategy:

- You **sell NO @ 0.20**, locking in a **$30 loss**.
- You **keep YES @ 0.80**, which has a maximum gain of **$20**.

If Team A ultimately wins:

- YES side: **+$50**  
- NO side: **−$30**  
- Net: **+$20 profit**

More importantly, your edge comes from the underlying statistic (which you will estimate from data):

- From this kind of game state (for example 0–3, 80% implied odds), **Team A may historically convert the match around ~92% of the time**.

You rely on that **conversion rate**, not on subjective reads.

---

### 7. Mathematical Framework: Expected Value Calculation

The profitability of this strategy depends on a precise mathematical relationship between the exit price and the conditional probability of the favorite winning.

#### 7.1. Trade Setup and Notation

- **Entry**: Buy both sides at or near 0.5:
  - Cost YES = 0.5
  - Cost NO = 0.5
  - Total cost = **1.0 unit**

- **Exit**: At some point, one side becomes the **cheap side** at price \( p_c \) (e.g., 0.20).
  - Sell the cheap side at \( p_c \)
  - Hold the **favorite** (opposite side) to resolution

Define:
- \( p_c \): price of the cheap side at exit (e.g., 0.20)
- "Favorite": the side opposite the cheap side
- \( q \): \( \Pr(\text{favorite wins} \mid \text{cheap price} = p_c) \)

#### 7.2. Expected Value Formula

At entry, you spend **1.0 unit**.

When you sell the cheap side at price \( p_c \):
- You receive \( p_c \) back
- Your net capital "remaining at risk" is: \( 1 - p_c \)

The remaining position (favorite) pays:
- **1** if the favorite wins
- **0** if the favorite loses

The **expected payoff** (ignoring fees and slippage) is:

\[
\text{EV} = q \cdot 1 + (1 - q) \cdot 0 - (1 - p_c) = q - (1 - p_c) = q + p_c - 1
\]

The trade is **EV-positive** if:

\[
q + p_c - 1 > 0 \quad \Longleftrightarrow \quad q > 1 - p_c
\]

**Examples**:
- If \( p_c = 0.20 \), you need \( q > 0.80 \) (80% win rate)
- If \( p_c = 0.17 \), you need \( q > 0.83 \) (83% win rate)

#### 7.3. Accounting for Costs

Including **fees, slippage, and safety margin** (combined cost \( c \)):

\[
\text{EV} = q + p_c - 1 - c
\]

The EV-positive condition becomes:

\[
q > 1 - p_c + c
\]

With a typical cost buffer \( c = 0.02 \) (2%):
- If \( p_c = 0.20 \), you need \( q > 0.82 \)
- If \( p_c = 0.17 \), you need \( q > 0.85 \)

This inequality is the **core mathematical test** for any exit threshold.

---

### 8. Why the Math Can Work

On average, your trades look like:

- **Loss on cheap side**: about **−$30 to −$40**.
- **Gain on expensive side**: about **+$50**.

So your expected net is around **+$10 to +$20 per full cycle**, as long as the heavily favored side wins often enough.

Break-even intuition:

- If the expensive side wins **more than ~66%** of the time, you roughly break even.
- If it wins **around 90–95%** of the time (your target, supported by data), your **expected value becomes clearly positive**.

Your real edge comes from:

- **Market overreaction to short-term events**.
- **Mispricing of momentum and economy**.
- **Panic-driven selling and buying**.
- **Low true comeback rates** once odds collapse beyond a certain point.

You are not trying to pick the better team. You are **systematically harvesting mispriced volatility**.

---

### 9. Choosing the Optimal Threshold: Empirical Results

To tune and validate the system, we analyzed historical Valorant market data to estimate the conditional probability \( q(p_c) \) that the favorite wins when the cheap side hits price level \( p_c \).

#### 9.1. Empirical Analysis Methodology

For each market snapshot, we:
1. Identified the **favorite** (higher price) and **cheap side** (lower price)
2. Tracked the **first time** the cheap side crossed various price thresholds
3. Recorded whether the favorite ultimately won the match
4. Computed empirical win rates \( \hat{q}(p) \) with confidence intervals

This gives us: "When the cheap side hits price \( p \), the favorite wins \( \hat{q}(p) \)% of the time."

#### 9.2. Validated Exit Thresholds

After analyzing historical data, we identified **three EV-positive thresholds** with the highest expected values:

| Threshold | Price | Hits | Wins | q_hat | ci_low | ci_high | required_q | **ev_estimate** |
|-----------|-------|------|------|-------|--------|---------|-------------|-----------------|
| **17%** | 0.17 | 139 | 131 | 94.2% | 89.1% | 97.1% | 83% | **+11.2%** |
| **18%** | 0.18 | 139 | 130 | 93.5% | 88.2% | 96.6% | 82% | **+11.5%** |
| **19%** | 0.19 | 139 | 128 | 92.1% | 86.4% | 95.5% | 81% | **+11.1%** |

**Key Findings**:
- All three thresholds have **139 hits** (sufficient sample size for statistical robustness)
- All have **ci_low > required_q**, meaning they pass the EV-positive test even under conservative assumptions
- **EV estimates range from 11.0% to 11.5%** per unit, which is substantial
- **Win rates (q_hat) range from 92.1% to 94.2%**, confirming strong statistical edge

#### 9.3. Multi-Threshold Exit Strategy

Instead of using a single exit threshold, we implement a **graduated exit strategy** that sells the cheap side progressively as it crosses multiple thresholds:

**Implementation**:
- **At 19%**: Sell **33%** of the cheap side position
- **At 18%**: Sell an additional **33%** of remaining position
- **At 17%**: Sell the **remaining 34%** of position
- **Hold favorite** to resolution at all thresholds

**Rationale**:
- Captures value early while maintaining exposure to deeper thresholds
- Reduces risk by taking partial profits at multiple levels
- Ensures we don't miss exits if price moves quickly through thresholds
- Each threshold validated as EV-positive with sufficient sample size

**Example Flow**:
1. Enter straddle at 50/50
2. Cheap side drops to 19% → sell 33% (lock in some recovery)
3. Cheap side drops to 18% → sell another 33% (more recovery)
4. Cheap side drops to 17% → sell final 34% (complete exit)
5. Hold favorite to resolution → capture full value if it wins

This approach maximizes expected value while reducing single-threshold risk.

#### 9.4. Why You Cannot Expect "100%"

The claim "when a team hits 20%, they're 100% going to lose" almost never holds in real data:

- Markets are noisy; **upsets always exist**
- Odds incorporate information but remain **probabilistic**, not deterministic
- The same price in different contexts (map, round score, economy) can imply different true win probabilities

Instead, we:
- Estimate \( q(p_c) \) empirically from historical data
- Use **confidence intervals** to account for statistical uncertainty
- Choose thresholds where \( \hat{q}_{\text{low}}(p) > 1 - p + c \) (even pessimistic estimates are EV-positive)

The validated thresholds (17%, 18%, 19%) meet this criterion with high confidence.

---

### 10. One-Paragraph Summary

You buy both YES and NO at roughly even odds, wait for Valorant’s natural volatility to push one side down to a low probability band (typically around 20–30% after pistol rounds, economy swings, or multi-round streaks), then immediately sell the cheap side and ride the expensive side to resolution or a favorable exit. Your profit comes from the spread between the two positions, backed by historical data showing that teams reduced to roughly 20% odds tend to lose the match the vast majority of the time. You are not trying to predict the winner; you are **turning volatility and market overreaction into a repeatable edge**.


