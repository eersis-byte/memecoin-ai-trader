"""DexScreener discovery; never claims that search is a complete market feed."""
import math
import time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import quote
import requests
from config import API, PROFILES, SEEDS


def number(value, default=0.0):
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError, OverflowError):
        return default


def fetch_json(url, *, session=None):
    getter = session or requests
    response = getter.get(url, timeout=12, headers={"User-Agent": "MemeCoinPaperResearch/1.5"})
    response.raise_for_status()
    return response.json()


def extract(pair, observed_at=None):
    base = pair.get("baseToken") or {}
    address = base.get("address")
    pair_address = pair.get("pairAddress")
    if not address or not pair_address or pair.get("chainId") != "solana":
        return None
    created = number(pair.get("pairCreatedAt"))
    now = observed_at or time.time()
    age = max(0, (now * 1000 - created) / 3600000) if created > 0 else None
    tx = (pair.get("txns") or {}).get("h1") or {}
    buys = max(0, int(number(tx.get("buys"))))
    sells = max(0, int(number(tx.get("sells"))))
    activity = buys + sells
    liquidity = max(0, number((pair.get("liquidity") or {}).get("usd")))
    price = number(pair.get("priceUsd"))
    change = number((pair.get("priceChange") or {}).get("h1"))
    score = round(100 * (0.45 * max(0, 1 - abs(change - 4) / 12) + 0.30 * buys / max(1, activity) + 0.25 * min(1, liquidity / 500000)), 1)
    return {"symbol": str(base.get("symbol") or "?"), "name": str(base.get("name") or ""),
            "address": str(address), "pair": str(pair_address), "price": price,
            "liquidity": liquidity, "volume24h": max(0, number((pair.get("volume") or {}).get("h24"))),
            "change1h": change, "transactions1h": activity, "age_hours": round(age, 2) if age is not None else None,
            "score": score, "url": pair.get("url"), "quote_time": datetime.fromtimestamp(now, timezone.utc).isoformat()}


def evaluate(token, profile):
    limits = PROFILES[profile]
    reasons = []
    if token["price"] <= 0: reasons.append("Invalid USD price")
    if token["liquidity"] < limits.liquidity: reasons.append("Insufficient liquidity")
    if token["volume24h"] < limits.volume: reasons.append("Insufficient 24h volume")
    if token["transactions1h"] < limits.transactions: reasons.append("Insufficient hourly transactions")
    if token["age_hours"] is None: reasons.append("Unknown pair age")
    elif token["age_hours"] < limits.min_age: reasons.append("Pair too new")
    return reasons


def scan(profile="Conservative", *, session=None, seeds=None):
    if profile not in PROFILES: raise ValueError("Unknown profile")
    selected, searches, total_pairs = {}, [], 0
    for term in seeds if seeds is not None else SEEDS:
        entry = {"term": term, "status": "ok", "pairs": 0}
        try:
            payload = fetch_json(f"{API}/latest/dex/search?q={quote(term)}", session=session)
            if not isinstance(payload, dict) or not isinstance(payload.get("pairs"), (list, type(None))):
                raise ValueError("Malformed API response")
            pairs = payload.get("pairs") or []
            entry["pairs"] = len(pairs)
            total_pairs += len(pairs)
            for pair in pairs:
                if not isinstance(pair, dict) or pair.get("chainId") != "solana": continue
                base = pair.get("baseToken") or {}
                address = base.get("address")
                if not address or not pair.get("pairAddress"): continue
                key = str(address)
                old = selected.get(key)
                # Do not prefer a high-liquidity pool if it has no usable USD price.
                rank = (number(pair.get("priceUsd")) > 0, number((pair.get("liquidity") or {}).get("usd")))
                old_rank = ((number(old.get("priceUsd")) > 0), number((old.get("liquidity") or {}).get("usd"))) if old else (-1, -1)
                if rank > old_rank: selected[key] = pair
        except (requests.RequestException, ValueError, TypeError) as exc:
            entry["status"] = f"{type(exc).__name__}: {exc}"
        searches.append(entry)
    tokens = []
    for pair in selected.values():
        try:
            token = extract(pair)
            if token:
                reasons = evaluate(token, profile)
                token.update(eligible=not reasons, reasons="; ".join(reasons))
                tokens.append(token)
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
    tokens.sort(key=lambda x: (x["eligible"], x["score"]), reverse=True)
    counts = Counter(reason for t in tokens for reason in t["reasons"].split("; ") if reason)
    stats = {"raw_pairs": total_pairs, "unique_tokens": len(tokens),
             "eligible": sum(t["eligible"] for t in tokens), "rejections": dict(counts),
             "searches": searches, "profile": profile,
             "searched_at": datetime.now(timezone.utc).isoformat(),
             "complete": bool(total_pairs) and all(s["status"] == "ok" for s in searches)}
    return tokens, stats


def refresh_positions(positions, *, session=None):
    """Refresh each held mint independently; fail closed if any quote cannot be trusted."""
    quotes, errors = {}, []
    for address, position in positions.items():
        try:
            payload = fetch_json(f"{API}/token-pairs/v1/solana/{quote(address)}", session=session)
            if not isinstance(payload, list): raise ValueError("Malformed pair response")
            # Lock to the entry pool: do not silently mark positions against another pool.
            matches = [p for p in payload if isinstance(p, dict) and p.get("chainId") == "solana"
                       and p.get("pairAddress") == position.get("pair") and number(p.get("priceUsd")) > 0]
            if not matches:
                errors.append(f"{address[:8]}: entry pool has no valid quote")
                continue
            quotes[address] = {"price": number(matches[0]["priceUsd"]), "time": datetime.now(timezone.utc).isoformat(),
                               "pair": position["pair"]}
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            errors.append(f"{address[:8]}: {type(exc).__name__}")
    return quotes, errors
