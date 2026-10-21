# MemeCoin AI Trader 1.4 — Solana paper simulator

No wallet, exchange API keys, or real-money orders. This is a **rule-based educational prototype**, not trained AI.

## Deploy on Streamlit Community Cloud
Upload `dashboard.py`, `trader.py`, and `requirements.txt` to the **root** of the existing GitHub repository, replacing the old files. Streamlit main file: `dashboard.py`, branch `main`.

## Run locally
```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

## What's new
- 18 seed search terms; still **not** a comprehensive token launch feed.
- Conservative and Exploratory paper-only eligibility profiles. No reduction in account exposure limits.
- Search diagnostics and **all discovered tokens**, including rejection reasons.
- One-click *manual* simulated trading cycle, with persistent status on the app (until local state is lost).
- Independent held-position price checks; cancel cycles when required market data is incomplete.
- Downloadable JSON paper account backups and CSV scan results.

## Critical limitations
- The app is **public** and state is stored in a **temporary local JSON file** shared among visitors. It can be reset by redeploys/restarts, and concurrent sessions are not isolated. This is NOT a secure or durable trading ledger. Download backups after each test. Real persistence needs an external database with authentication and per-user isolation.
- Simulated prices are snapshots; estimated 1% per-side costs may understate slippage, MEV, failed exits, and illiquidity. Stop-losses are only checked during manual cycles and may not execute at the displayed price.
- Search results may contain fake tokens or spoofed symbols. No honeypot, rug-pull, mint/freeze-authority, contract, holder-concentration or transaction simulation checks are implemented. Do not infer safety from the heuristic score.
- No background worker; pressing the button performs **one** manual cycle. No real money should be connected to this prototype.
- Changing the profile does not retroactively modify positions; it changes new-entry eligibility. The app preserves the existing account exposure rules (5% equity per position, four positions maximum, 3% daily drawdown entry halt).
