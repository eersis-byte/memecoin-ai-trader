# MemeCoin AI Trader 1.2 — Paper only

Upload the four files in this folder to the ROOT of your existing `memecoin-ai-trader` GitHub repository, replacing files of the same names. Streamlit entrypoint: `dashboard.py` on `main`.

The Discovery Scanner searches 14 seed terms and shows all returned Solana tokens, even those that fail eligibility checks. A separate button runs **one** paper-trading cycle using fresh search results and independent held-token quotes. Each trade is simulated. There is no wallet integration or live execution.

**Important:** Streamlit Community Cloud local filesystem is ephemeral. Paper trades may disappear after redeploy, restart, or moving to another server replica. For trustworthy long-term tracking, use an external durable database and a single worker. Do not run concurrent paper cycles; this prototype does not lock state against multiple users/sessions. A public app allows visitors to trigger simulated cycles on the shared instance.

Trade model uses 1% estimated cost on each side, up to 5% equity per position, 4 positions, score >=70, 8% stop, 16% target, 10% trailing stop, and a daily-entry cutoff after 3% equity decline. These are not guaranteed execution limits or a validated profitable strategy. Market data can be missing or misleading. Never upload secrets or connect real funds.

Local one-shot command: `python trader.py --once`. To view locally: `streamlit run dashboard.py`.
