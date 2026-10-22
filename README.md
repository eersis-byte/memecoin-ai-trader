# MemeCoin AI Trader 1.5 — Foundation Release

**Research and manual PAPER TRADING only.** No wallet keys, no order placement, no guarantee of returns, and no trained AI in this release.

## What changed from 1.4

- Three profiles: Conservative, Balanced, Exploratory paper; no arbitrary maximum pair age.
- Separate Solana mint and liquidity-pool identity; do not mark held positions using a different pool.
- Fail-closed market feed and held-position quotes; quote-age limit 180 seconds; no stale fallback equity.
- Gap-aware observed-price stop triggers (not guaranteed stop-loss fills), daily loss entry halt and 5% maximum position size.
- Explicit paper-only opt-in required to trade when mint authority risk is unknown. Limited optional Solana RPC mint/freeze authority checks; known dangerous authorities block paper entry.
- Password-protected Streamlit access and per-user database account rows; transactional, idempotent cycle storage and decision journal.
- Snapshot capture and three-profile replay. Replay uses recorded snapshots, is in-sample, has missing-quote gaps and does **not** establish profitability.
- Paper trades still use approximate 1% entry and 1% exit costs; actual impact, tax, MEV, latency, and unfillable markets are not modeled.

## Deploy on GitHub + Streamlit

1. Upload `dashboard.py`, `config.py`, `market.py`, `engine.py`, `storage.py`, `security.py`, `backtest.py`, `auth.py`, `requirements.txt`, `.gitignore`, `README.md` and `tests/` to the **repository root**. Replace old `dashboard.py` and `trader.py` if necessary; the old `trader.py` is no longer imported. Keep `requirements-dev.txt` for local testing.
2. Generate a secure password hash on your computer with `python auth.py` (Python 3.10+). Enter a long password when prompted. Save the printed hash; **do not** save the plaintext password to GitHub.
3. In Streamlit Cloud > Manage app > Settings > Secrets, paste this template (replace the hash and database URL):

```toml
DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require"
# Optional; configure with your own trusted RPC provider:
# SOLANA_RPC_URL = "https://YOUR-SOLANA-RPC-ENDPOINT"
[users]
owner = "pbkdf2_sha256$310000$YOUR_SALT_HEX$YOUR_HASH_HEX"
```

4. **Use external PostgreSQL** for durable storage on Streamlit Community Cloud. SQLite is a fallback for local development only; Streamlit Cloud's filesystem can reset. Obtain a managed PostgreSQL connection string from a trusted provider; do not commit it. The app creates four tables on startup. It needs table creation and read/write permissions.
5. Confirm the Streamlit deployment points to branch `main`, entrypoint `dashboard.py`. Deploy/reboot, sign in with `owner` and the password you chose.
6. Click **Fetch and record market snapshot**, then **Run one paper trading cycle**. With default security settings, unverified mints will not be paper-bought. For testing only, you can explicitly enable the research-only unknown-risk opt-in; this is not a token-safety approval.
7. After recording multiple observations over time, use **Compare three profiles on recorded snapshots**. This is replay, not true independent backtesting.

### No existing Version 1.4 paper-state migration

Version 1.5 starts a **new** account with $1,000. Save the 1.4 JSON backup separately. Do not assume a local JSON file has been migrated to PostgreSQL. Import/migration requires a separately tested feature.

### Run tests locally

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Known limitations and roadmap

- **Not implemented:** automated unattended worker, Telegram/email alerts, social-media sentiment, trained ML model, holder concentration, liquidity lock checks, transfer simulation/honeypot detection, Token-2022 extension validation, historical candle ingestion, and real exchange execution.
- RPC mint/freeze checks are **partial** and can be unavailable; even a `limited_pass` is not a safety guarantee.
- User passwords use salted PBKDF2 hashes in Streamlit Secrets. For a public production app, use managed authentication with MFA, session expiration, login rate limiting, and audit logs. This demo does not implement these protections.
- Search terms are broader but still **not** an exhaustive new-token feed. Rate limits and outages may block cycles.
- Concurrent updates are rejected instead of silently overwriting another session. Each successful cycle is an atomic database transaction.
- Snapshot replay uses the same observations to select and evaluate opportunities, which can introduce optimistic assumptions. It skips missing held-token quotes; only time-separated snapshots are meaningful. Build a dedicated forward-test and delayed-fill engine before evaluating predictive models.
- Do not connect wallet credentials or use the code for live trading.

### Next stages

1. Validate durable PostgreSQL operation and implement managed authentication plus snapshot retention policy.
2. Add audited, independently sourced token-risk signals and richer market feeds.
3. Add replay with explicit next-snapshot execution, out-of-sample windows, and walk-forward validation.
4. Add opt-in Telegram/email notifications with secret-safe delivery, rate limiting and error handling.
5. Add properly licensed and timestamped social data; then train/evaluate an ML ranker against a non-ML baseline, with leakage controls and realistic costs.
