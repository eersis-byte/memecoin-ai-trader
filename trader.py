"""Educational Solana meme-token paper trader. No wallet, orders or AI profit claims."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

API = 'https://api.dexscreener.com'
STATE = Path(os.environ.get('TRADER_STATE', 'paper_state.json'))
SEEDS = ['SOL', 'BONK', 'WIF', 'POPCAT', 'FARTCOIN', 'PENGU']
STARTING_CASH = 1000.0
MAX_POSITION_FRACTION = 0.05
MAX_OPEN_POSITIONS = 4
MAX_DAILY_LOSS = 0.03
STOP_LOSS = 0.08
TAKE_PROFIT = 0.16
TRAILING_STOP = 0.10
ESTIMATED_ROUND_TRIP_COST = 0.02  # 1% each side; simplified fee + slippage model


def get_json(url):
    r = requests.get(url, timeout=15, headers={'User-Agent': 'EducationalPaperTrader/1.0'})
    r.raise_for_status()
    return r.json()


def scan(diagnostics=False):
    """Return qualified Solana pairs, optionally with diagnostic information."""
    from collections import Counter
    from urllib.parse import quote

    stats = {'searches': [], 'raw_pairs': 0, 'solana_pairs': 0,
             'unique_tokens': 0, 'rejections': {}, 'qualified': 0}
    pairs = {}
    rejected = Counter()

    for symbol in SEEDS:
        entry = {'term': symbol, 'status': 'ok', 'pairs': 0}
        try:
            payload = get_json(f'{API}/latest/dex/search?q={quote(symbol)}')
            if not isinstance(payload, dict):
                raise ValueError('Unexpected API response format')
            found = payload.get('pairs') or []
            entry['pairs'] = len(found)
            stats['raw_pairs'] += len(found)
            for p in found:
                if p.get('chainId') != 'solana':
                    continue
                stats['solana_pairs'] += 1
                address = (p.get('baseToken') or {}).get('address')
                if not address:
                    continue
                # Keep the most liquid pair per token, not the first search hit.
                old = pairs.get(address)
                liq = float((p.get('liquidity') or {}).get('usd') or 0)
                old_liq = float((old.get('liquidity') or {}).get('usd') or 0) if old else -1
                if liq > old_liq:
                    pairs[address] = p
        except (requests.RequestException, ValueError, TypeError) as exc:
            entry['status'] = f'{type(exc).__name__}: {exc}'
        stats['searches'].append(entry)

    stats['unique_tokens'] = len(pairs)
    results = []
    for p in pairs.values():
        try:
            liquidity = float((p.get('liquidity') or {}).get('usd') or 0)
            volume = float((p.get('volume') or {}).get('h24') or 0)
            change = float((p.get('priceChange') or {}).get('h1') or 0)
            price = float(p.get('priceUsd') or 0)
            tx = (p.get('txns') or {}).get('h1') or {}
            buys = int(tx.get('buys') or 0)
            sells = int(tx.get('sells') or 0)
            created = p.get('pairCreatedAt')
            age_hours = ((time.time() * 1000 - int(created)) / 3600000) if created else None
            if price <= 0:
                rejected['missing/zero price'] += 1
            elif liquidity < 50000:
                rejected['liquidity under $50k'] += 1
            elif volume < 100000:
                rejected['24h volume under $100k'] += 1
            elif age_hours is None:
                rejected['unknown pair age'] += 1
            elif not (24 <= age_hours <= 24 * 365):
                rejected['pair age outside 1 day–1 year'] += 1
            elif buys + sells < 30:
                rejected['under 30 hourly transactions'] += 1
            else:
                momentum = max(0, 1 - abs(change - 4) / 12)
                activity = buys / max(1, buys + sells)
                liquidity_score = min(1, liquidity / 500000)
                score = round(100 * (0.45 * momentum + 0.30 * activity + 0.25 * liquidity_score), 1)
                base = p.get('baseToken') or {}
                results.append({'symbol': base.get('symbol', '?'), 'name': base.get('name', ''),
                                'address': base['address'], 'pair': p.get('pairAddress'),
                                'price': price, 'liquidity': liquidity, 'volume24h': volume,
                                'change1h': change, 'score': score, 'url': p.get('url')})
        except (TypeError, ValueError, KeyError, OverflowError) as exc:
            rejected['malformed pair data'] += 1
    stats['rejections'] = dict(rejected)
    stats['qualified'] = len(results)
    results.sort(key=lambda x: x['score'], reverse=True)
    return (results, stats) if diagnostics else results


def default_state():
    return {'cash': STARTING_CASH, 'positions': {}, 'trades': [], 'equity_history': [], 'day_start': {}}


def load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return default_state()


def save(state):
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(state, indent=2))
    temp.replace(STATE)


def equity(state, prices):
    return state['cash'] + sum(pos['units'] * prices.get(addr, pos['last_price']) for addr, pos in state['positions'].items())


def step(state, tokens):
    now = datetime.now(timezone.utc).isoformat()
    today = now[:10]
    prices = {t['address']: t['price'] for t in tokens}
    # Stale quotes are not treated as current; do not exit on an unobserved price.
    for addr, pos in list(state['positions'].items()):
        if addr not in prices:
            continue
        price = prices[addr]
        pos['last_price'] = price
        pos['peak_price'] = max(pos['peak_price'], price)
        if price <= pos['entry_price'] * (1 - STOP_LOSS):
            reason = 'stop loss'
        elif price >= pos['entry_price'] * (1 + TAKE_PROFIT):
            reason = 'take profit'
        elif price <= pos['peak_price'] * (1 - TRAILING_STOP):
            reason = 'trailing stop'
        else:
            continue
        proceeds = pos['units'] * price * (1 - ESTIMATED_ROUND_TRIP_COST / 2)
        state['cash'] += proceeds
        state['trades'].append({'time': now, 'side': 'SELL', 'symbol': pos['symbol'], 'address': addr,
                                'price': price, 'value': round(proceeds, 2), 'pnl': round(proceeds - pos['cost'], 2), 'reason': reason})
        del state['positions'][addr]
    total = equity(state, prices)
    state['day_start'].setdefault(today, total)
    daily_floor = state['day_start'][today] * (1 - MAX_DAILY_LOSS)
    if total > daily_floor:
        for t in tokens:
            if len(state['positions']) >= MAX_OPEN_POSITIONS or t['score'] < 70:
                break
            addr = t['address']
            if addr in state['positions']:
                continue
            # Limit exposure to 5% of equity per position, and only enter if sufficient cash.
            allocation = min(total * MAX_POSITION_FRACTION, state['cash'])
            if allocation < 10:
                break
            entry_cost = allocation
            units = allocation * (1 - ESTIMATED_ROUND_TRIP_COST / 2) / t['price']
            state['cash'] -= allocation
            state['positions'][addr] = {'symbol': t['symbol'], 'units': units, 'cost': entry_cost,
                                        'entry_price': t['price'], 'last_price': t['price'],
                                        'peak_price': t['price'], 'entered': now}
            state['trades'].append({'time': now, 'side': 'BUY', 'symbol': t['symbol'], 'address': addr,
                                    'price': t['price'], 'value': round(allocation, 2), 'pnl': None, 'reason': 'score threshold'})
    state['equity_history'].append({'time': now, 'equity': round(equity(state, prices), 2)})
    state['equity_history'] = state['equity_history'][-10000:]
    return state


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true', help='Run one scan and simulation step')
    parser.add_argument('--interval', type=int, default=60, help='Polling interval in seconds')
    args = parser.parse_args()
    while True:
        tokens = scan()
        state = step(load(), tokens)
        save(state)
        print(f"{datetime.now(timezone.utc).isoformat()} candidates={len(tokens)} cash=${state['cash']:.2f} positions={len(state['positions'])} equity=${state['equity_history'][-1]['equity']:.2f}", flush=True)
        if args.once:
            break
        time.sleep(max(30, args.interval))
