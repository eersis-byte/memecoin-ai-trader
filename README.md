# MemeCoin AI Trader 1.0 — Paper Trading Prototype

This is an **educational Solana meme-token scanner and paper trading simulator**, not a validated profitable strategy or a trained AI model. **No wallet keys, exchange account, or real orders are supported.**

## Setup

Requires Python 3.10+ and internet access to DexScreener.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python trader.py --once
streamlit run dashboard.py
```

For repeated paper-trading scans, run `python trader.py --interval 60` in a separate terminal. Keep only one trader process running per state file. Dashboard reads the saved results; use the dashboard's button for a fresh candidate scan.

## Strategy and limits

- Searches a limited seed-symbol universe on DexScreener; this is **not** comprehensive new-token discovery.
- Filters by minimum $50k liquidity, $100k 24-hour volume, at least 30 hourly transactions, and token-pair age of 1–365 days.
- Scores momentum, buy/sell transaction count ratio, and liquidity. Buys when heuristic score >=70.
- Starts with $1,000 virtual cash; limits position size to 5% of equity and at most 4 positions.
- Exit conditions: 8% stop loss, 16% take profit, or 10% trailing stop, evaluated only at observed snapshots.
- Estimates 1% entry and 1% exit friction, not real execution impact.
- Prevents new entries after a 3% simulated daily equity drawdown relative to the first observation of that UTC day. **This is not a guaranteed maximum loss**, and it does not force liquidations.

## Known limitations / next steps

- Scores are simple rules, **not machine learning**. Future model development requires historical data and out-of-sample validation.
- DexScreener API availability, limits, and returned fields may change.
- No contract safety analysis, honeypot checks, token freeze authority checks, holder concentration, wash-trading detection, or independent pool verification.
- No historical backtest, trade-by-trade fill simulation, robust stale-price valuation, transaction taxes, MEV, priority fees, market impact, or tax reporting.
- The simulator can materially overstate results; low-liquidity tokens may be impossible to exit near quoted prices.
- Not suitable for real-money deployment without a substantially stronger safety, testing, and execution system.
