"""Replay recorded snapshots only. This is NOT independent out-of-sample validation."""
from datetime import datetime
from config import PROFILES
from engine import cycle
from storage import default_state


def replay(snapshots, profile, *, allow_unverified=True):
    if profile not in PROFILES: raise ValueError("Unknown profile")
    # No history is downloaded or fabricated. One snapshot is insufficient.
    if len(snapshots) < 2:
        return {"status": "insufficient_data", "message": "Record at least two separate market snapshots."}
    state = default_state(); completed = skipped = 0
    # Snapshots are sorted by actual recorded time; duplicate timestamps ignored.
    seen = set()
    for recorded_at, tokens in sorted(snapshots, key=lambda item: item[0]):
        now = datetime.fromisoformat(recorded_at)
        if now.tzinfo is None or recorded_at in seen: continue
        seen.add(recorded_at)
        if not isinstance(tokens, list): continue
        # Replay price only at recorded time. Market snapshots are observations,
        # not executable quotes. Mark-to-market is approximate.
        current = {t.get("address"): t for t in tokens if isinstance(t, dict)}
        quotes = {}
        for addr, pos in state["positions"].items():
            t = current.get(addr)
            if t and t.get("pair") == pos["pair"] and t.get("price", 0) > 0:
                quotes[addr] = {"price": t["price"], "pair": pos["pair"], "time": recorded_at}
        if len(quotes) != len(state["positions"]):
            skipped += 1; continue
        # Use the timestamp of the observation, not the time a CSV was exported.
        observed = [{**t, "quote_time": recorded_at} for t in tokens if isinstance(t, dict)]
        state, _, status = cycle(state, observed, quotes, profile, now=now, allow_unverified=allow_unverified)
        if status == "completed": completed += 1
        else: skipped += 1
    if completed < 2:
        return {"status": "insufficient_data", "message": "Fewer than two usable sequential observations", "skipped": skipped}
    eq = [e["equity"] for e in state["equity_history"]]
    peak = eq[0]; max_dd = 0.0
    for value in eq:
        peak = max(peak, value)
        max_dd = max(max_dd, (peak-value)/peak if peak else 0)
    sells = [t for t in state["trades"] if t["side"] == "SELL"]
    return {"status": "ok", "profile": profile, "cycles": completed, "skipped": skipped,
            "equity": eq[-1], "cash": state["cash"], "open_positions": len(state["positions"]),
            "closed_trades": len(sells), "win_rate": (sum(t["pnl"]>0 for t in sells)/len(sells)) if sells else None,
            "max_drawdown": round(max_dd, 4), "equity_history": state["equity_history"],
            "warning": "In-sample snapshot replay only. Missing prices skip cycles; fills and costs are approximations. Not a historical exchange backtest."}
