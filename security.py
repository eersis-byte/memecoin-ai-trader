"""Limited on-chain authority checks; NOT a rug-pull or honeypot certification."""
import requests


def check_mint(mint, rpc_url, *, session=None):
    if not rpc_url:
        return {"status": "unknown", "reason": "Solana RPC not configured; no on-chain verification"}
    getter = session or requests
    try:
        response = getter.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
            "params": [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}]}, timeout=8)
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"): raise ValueError("RPC returned an error")
        value = (payload.get("result") or {}).get("value")
        if not value: return {"status": "blocked", "reason": "Mint account not found"}
        parsed = (value.get("data") or {}).get("parsed") or {}
        if parsed.get("type") != "mint": return {"status": "blocked", "reason": "Account is not a parsed mint"}
        info = parsed.get("info") or {}
        if info.get("mintAuthority") is not None: return {"status": "blocked", "reason": "Mint authority enabled"}
        if info.get("freezeAuthority") is not None: return {"status": "blocked", "reason": "Freeze authority enabled"}
        if not isinstance(info.get("decimals"), int): return {"status": "unknown", "reason": "Mint metadata incomplete"}
        # Extensions, concentration, LP custody, and transfer behavior not verified.
        return {"status": "limited_pass", "reason": "Mint/freeze authorities disabled; other risks unverified"}
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return {"status": "unknown", "reason": "RPC check unavailable or malformed"}
