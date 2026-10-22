"""Version 1.5 foundation: authenticated, manual, paper-only Streamlit app."""
import os
import uuid
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from auth import verify
from config import PROFILES, STARTING_CASH
from market import scan, refresh_positions
from engine import cycle
from storage import Store
from security import check_mint
from backtest import replay

st.set_page_config(page_title="MemeCoin AI Trader 1.5 — Paper", layout="wide")
st.title("MemeCoin AI Trader 1.5")
st.caption("RESEARCH + MANUAL PAPER TRADING ONLY · No wallet, exchange access, or real-money orders")

# Refuse to run an unauthenticated public trading dashboard.
try:
    accounts = dict(st.secrets["users"])
except (KeyError, FileNotFoundError):
    st.error("Access not configured. Add [users] password hashes to Streamlit Secrets. See README.")
    st.stop()
if not accounts:
    st.error("No users configured. See README."); st.stop()
if "user" not in st.session_state:
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        if username in accounts and verify(password, accounts[username]):
            st.session_state.user = username
            st.rerun()
        else:
            st.error("Invalid credentials")
    st.stop()
user = st.session_state.user
if user not in accounts:
    st.session_state.pop("user", None); st.rerun()
with st.sidebar:
    st.write(f"Signed in as **{user}**")
    if st.button("Sign out"):
        st.session_state.clear(); st.rerun()

try:
    db_url = st.secrets.get("DATABASE_URL", os.environ.get("DATABASE_URL", ""))
    store = Store(db_url or None)
except Exception as exc:
    st.error(f"Database unavailable: {type(exc).__name__}. Check DATABASE_URL and schema permissions.")
    st.stop()
if not store.durable:
    st.warning("SQLite is in use: on Streamlit Community Cloud this database is TEMPORARY. Configure an external PostgreSQL DATABASE_URL before trusting records across restarts.")
st.error("Security checks are LIMITED: holder concentration, LP custody, Token-2022 extensions, transfer taxes and honeypot behavior are not verified. Paper trading only.")

profile = st.selectbox("Paper eligibility profile", list(PROFILES))
limits = PROFILES[profile]
st.caption(f"{profile}: liquidity ≥ ${limits.liquidity:,.0f}; volume ≥ ${limits.volume:,.0f}; hourly trades ≥ {limits.transactions}; age ≥ {limits.min_age}h; score ≥ {limits.min_score}. No maximum pair age.")
allow_unknown = st.checkbox("Research-only: allow paper entries when mint authority status is unknown (higher risk)", value=False)
check_chain = st.checkbox("Check mint/freeze authorities via configured Solana RPC (slower)", value=False)
rpc_url = st.secrets.get("SOLANA_RPC_URL", "")
if check_chain and not rpc_url: st.warning("SOLANA_RPC_URL not configured; all mint statuses will be unknown.")
state, version = store.load(user)

st.subheader("Manual controls")
a, b = st.columns(2)
scan_click = a.button("Fetch and record market snapshot")
cycle_click = b.button("Run one paper trading cycle", type="primary")
if scan_click or cycle_click:
    with st.spinner("Retrieving market data..."):
        try:
            tokens, stats = scan(profile)
            st.session_state["last_scan"] = (tokens, stats)
            if scan_click:
                store.record_scan(user, tokens, profile)
                st.success(f"Recorded {len(tokens)} tokens in the research snapshot.")
            if cycle_click:
                if not stats["complete"]:
                    st.error("Cycle cancelled: search feed incomplete or unavailable. No account change.")
                else:
                    quotes, errors = refresh_positions(state["positions"])
                    if errors:
                        st.error("Cycle cancelled: held-position quotes missing or mismatched. " + "; ".join(errors))
                    else:
                        security = {}
                        if check_chain:
                            for t in tokens:
                                if t["eligible"] and t["score"] >= limits.min_score:
                                    security[t["address"]] = check_mint(t["address"], rpc_url)
                        updated, decisions, status = cycle(state, tokens, quotes, profile,
                            allow_unverified=allow_unknown, security=security)
                        if status != "completed":
                            st.error("Cycle cancelled: " + "; ".join(d["reason"] for d in decisions))
                        else:
                            previous = len(state["trades"])
                            trades = updated["trades"][previous:]
                            report = {"time": datetime.now(timezone.utc).isoformat(), "profile": profile,
                                      "discovered": len(tokens), "eligible": stats["eligible"],
                                      "buys": sum(t["side"] == "BUY" for t in trades),
                                      "sells": sum(t["side"] == "SELL" for t in trades),
                                      "decisions": len(decisions), "status": status}
                            updated["last_cycle"] = report
                            store.commit_cycle(user, version, str(uuid.uuid4()), updated, report, decisions, tokens, profile)
                            st.session_state["cycle_result"] = report
                            st.rerun()
        except Exception as exc:
            st.error(f"Action failed; no successful account commit confirmed: {type(exc).__name__}: {exc}")

state, _ = store.load(user)
report = st.session_state.get("cycle_result") or state.get("last_cycle")
if report:
    st.subheader("Last cycle result")
    st.success(f"{report['time']} · {report['profile']} · {report['status']}")
    c1,c2,c3,c4 = st.columns(4)
    for c, label, key in zip((c1,c2,c3,c4), ("Discovered", "Eligible", "Paper buys", "Paper sells"), ("discovered","eligible","buys","sells")):
        c.metric(label, report.get(key, 0))
    if not report.get("buys") and not report.get("sells"):
        st.info("No trades executed. See Decision journal for the exact reasons.")

st.subheader("Paper account")
last = state["equity_history"][-1]["equity"] if state["equity_history"] else STARTING_CASH
c1,c2,c3 = st.columns(3)
c1.metric("Last recorded equity (not a live valuation)", f"${last:,.2f}")
c2.metric("Cash", f"${state['cash']:,.2f}")
c3.metric("Open positions", len(state["positions"]))
if state["equity_history"]:
    history = pd.DataFrame(state["equity_history"])
    history["time"] = pd.to_datetime(history["time"], utc=True)
    st.line_chart(history.set_index("time")["equity"])
st.dataframe(pd.DataFrame([{"mint": a, **p} for a,p in state["positions"].items()]), width="stretch")
st.subheader("Trade log")
st.dataframe(pd.DataFrame(state["trades"][::-1]), width="stretch")
st.subheader("Decision journal")
st.dataframe(pd.DataFrame(store.journal(user)), width="stretch")

if "last_scan" in st.session_state:
    tokens, stats = st.session_state["last_scan"]
    st.subheader("Latest scanner results (this session)")
    c1,c2,c3 = st.columns(3)
    c1.metric("API pairs", stats["raw_pairs"])
    c2.metric("Distinct Solana mints", stats["unique_tokens"])
    c3.metric("Profile eligible", stats["eligible"])
    st.dataframe(pd.DataFrame(tokens), width="stretch")
    with st.expander("API errors and rejection reasons"):
        st.dataframe(pd.DataFrame(stats["searches"]), width="stretch")
        st.write(stats["rejections"])
    st.download_button("Export scan CSV", pd.DataFrame(tokens).to_csv(index=False), "memecoin_scan_v15.csv")

st.subheader("Snapshot replay laboratory")
st.caption("Uses only your account's recorded snapshots. No fabricated history or future prices. Missing held-position quotes skip observations.")
snapshots = store.snapshots(user)
st.write(f"Stored observations: {len(snapshots)}")
if st.button("Compare three profiles on recorded snapshots"):
    rows=[]
    for name in PROFILES:
        result = replay(snapshots, name)
        rows.append({k:v for k,v in result.items() if k != "equity_history"})
    st.dataframe(pd.DataFrame(rows), width="stretch")
st.caption("Future stages: independently verified token-risk providers, scheduled worker, alerts, social signals, and validated ML ranking. None are active in 1.5 foundation.")
