# MemeCoin AI Trader 1.1 — paper trading only

Upload `dashboard.py`, `trader.py`, and `requirements.txt` to the root of your existing GitHub repository, replacing the older versions. Streamlit entrypoint: `dashboard.py`.

Click **Fetch current candidates** to view the search diagnostics, filter rejection counts, and qualified Solana tokens. Search results are not trading signals. The dashboard does not execute trades.

The original command-line simulation is still available locally with `python trader.py --once`, but Streamlit Community Cloud does not automatically run it continuously or guarantee persistence of local state files.

No real money or wallet connections. This is a rule-based prototype, not trained AI. Public repositories must not contain secrets.
