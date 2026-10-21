# MemeCoin AI Trader 1.3

Educational Solana meme-token paper simulator. **No live orders or wallet access.**

## Deploy
Upload `dashboard.py`, `trader.py`, `requirements.txt`, and `README.md` to the root of the existing GitHub repository. Set Streamlit main file to `dashboard.py`. Commit changes; Streamlit should redeploy.

## Use
Click **Run one paper trading cycle**. The **Last cycle result** section shows the outcome, candidate counts, and trade counts without an immediate rerun hiding the message. A completed cycle with zero trades is valid: it may have found no eligible coins or no score of 70 or above. Use **Fetch current candidates** to see market diagnostics.

## Limitations
The last-cycle message is kept in browser session state only; it is not durable. The paper account is stored on the Streamlit server's temporary filesystem and can reset on restart; it is also shared by visitors to the public app. Do not rely on it for long-term or multi-user performance tracking. There is no background worker. A separate durable database, user authentication, and realistic backtesting are needed before serious evaluation. Never supply wallet secrets.
