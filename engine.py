"""Deterministic paper fills and audit trail; no live trading integrations."""
import copy
import math
from datetime import datetime, timezone
from config import (MAX_POSITION_FRACTION, MAX_OPEN_POSITIONS, MAX_DAILY_LOSS, STOP_LOSS,
                    TAKE_PROFIT, TRAILING_STOP, ONE_WAY_COST, MAX_QUOTE_AGE_SECONDS)
from market import evaluate


def valid_quote(quote, now):
    if not isinstance(quote, dict): return False
    try:
        price = float(quote["price"])
        stamp = datetime.fromisoformat(quote["time"])
        return math.isfinite(price) and price > 0 and stamp.tzinfo is not None and 0 <= (now - stamp).total_seconds() <= MAX_QUOTE_AGE_SECONDS
    except (KeyError, ValueError, TypeError, OverflowError): return False


def portfolio(state, quotes, now):
    """No stale fallback: return unknown equity if a held position has no fresh quote."""
    total = float(state["cash"])
    for address, pos in state["positions"].items():
        q = quotes.get(address)
        if not valid_quote(q, now) or q.get("pair") != pos.get("pair"):
            return None
        total += pos["units"] * q["price"]
    return total


def cycle(state, candidates, quotes, profile, *, now=None, allow_unverified=False, security=None):
    from config import PROFILES
    if profile not in PROFILES: raise ValueError("Unknown profile")
    now = now or datetime.now(timezone.utc)
    timestamp = now.isoformat(); today = now.date().isoformat()
    state = copy.deepcopy(state)
    state.setdefault("halted", False)
    if today not in state.get("day_start", {}):
        state["halted"] = False  # New UTC trading day; reset entry halt, not accumulated P&L.
    decisions = []
    security = security or {}
    start_equity = portfolio(state, quotes, now)
    if start_equity is None:
        return state, [{"address": "", "decision": "CANCEL", "reason": "Held-position quote missing, stale, or wrong pool"}], "cancelled"
    # Exit first. A quote gap can execute far beyond the configured stop threshold.
    for addr, pos in list(state["positions"].items()):
        q = quotes[addr]
        price = q["price"]
        pos["peak_price"] = max(pos.get("peak_price", pos["entry_price"]), price)
        reason = None
        if price <= pos["entry_price"] * (1 - STOP_LOSS): reason = "stop-loss trigger; executed at observed price"
        elif price >= pos["entry_price"] * (1 + TAKE_PROFIT): reason = "take-profit trigger"
        elif price <= pos["peak_price"] * (1 - TRAILING_STOP): reason = "trailing-stop trigger"
        pos["last_price"] = price
        if reason:
            proceeds = pos["units"] * price * (1 - ONE_WAY_COST)
            state["cash"] += proceeds
            state["trades"].append({"time": timestamp, "side": "SELL", "symbol": pos["symbol"], "address": addr,
                                    "pair": pos["pair"], "price": price, "value": round(proceeds, 2),
                                    "pnl": round(proceeds - pos["cost"], 2), "reason": reason})
            del state["positions"][addr]
            decisions.append({"address": addr, "decision": "SELL", "reason": reason})
    current = portfolio(state, quotes, now)
    if current is None: raise RuntimeError("Quote inconsistency after exits")
    state["day_start"].setdefault(today, start_equity)
    floor = state["day_start"][today] * (1 - MAX_DAILY_LOSS)
    if current <= floor:
        state["halted"] = True
        decisions.append({"address": "", "decision": "HALT", "reason": "Daily loss circuit breaker triggered; no new entries"})
    if not state["halted"]:
        for token in candidates:
            addr = token["address"]
            reasons = evaluate(token, profile)
            if token["score"] < PROFILES[profile].min_score: reasons.append("Below profile score threshold")
            if addr in state["positions"]: reasons.append("Already held")
            if len(state["positions"]) >= MAX_OPEN_POSITIONS: reasons.append("Position count limit")
            # Unknown / unverifiable authority risk is blocked unless user explicitly opts in for PAPER ONLY.
            risk = security.get(addr, {"status": "unknown", "reason": "No on-chain risk check"})
            if risk["status"] == "blocked": reasons.append("Authority risk: " + risk["reason"])
            if risk["status"] == "unknown" and not allow_unverified: reasons.append("Unverified mint authority status")
            if not valid_quote({"price": token.get("price"), "time": token.get("quote_time")}, now): reasons.append("Candidate quote stale")
            if reasons:
                decisions.append({"address": addr, "decision": "SKIP", "reason": "; ".join(reasons)})
                continue
            allocation = min(current * MAX_POSITION_FRACTION, state["cash"])
            if allocation < 10:
                decisions.append({"address": addr, "decision": "SKIP", "reason": "Insufficient cash or position allocation"})
                continue
            units = allocation * (1 - ONE_WAY_COST) / token["price"]
            state["cash"] -= allocation
            state["positions"][addr] = {"symbol": token["symbol"], "pair": token["pair"], "units": units,
                "cost": allocation, "entry_price": token["price"], "last_price": token["price"],
                "peak_price": token["price"], "entered": timestamp}
            state["trades"].append({"time": timestamp, "side": "BUY", "symbol": token["symbol"], "address": addr,
                "pair": token["pair"], "price": token["price"], "value": round(allocation, 2), "pnl": None,
                "reason": "Profile criteria met; simulated one-way cost 1%"})
            decisions.append({"address": addr, "decision": "BUY", "reason": "Profile and risk gates passed"})
    # Fresh snapshots from this scan are usable for newly opened positions.
    marks = dict(quotes)
    for t in candidates:
        if t["address"] in state["positions"] and t["address"] not in marks:
            marks[t["address"]] = {"price": t["price"], "time": t["quote_time"], "pair": t["pair"]}
    end_equity = portfolio(state, marks, now)
    if end_equity is not None:
        state["equity_history"].append({"time": timestamp, "equity": round(end_equity, 2)})
        state["equity_history"] = state["equity_history"][-10000:]
    return state, decisions, "completed"
