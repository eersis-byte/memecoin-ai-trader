"""MemeCoin AI Trader 1.2: educational Solana paper simulator. Never sends orders."""
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests

API = 'https://api.dexscreener.com'
STATE = Path(os.environ.get('TRADER_STATE', 'paper_state.json'))
SEEDS = ['BONK', 'WIF', 'POPCAT', 'FARTCOIN', 'PENGU', 'MEW', 'BOME', 'MOODENG', 'GOAT', 'PNUT', 'MICHI', 'MOG', 'TURBO', 'NEIRO']
STARTING_CASH = 1000.0
MAX_POSITION_FRACTION = .05
MAX_OPEN_POSITIONS = 4
MAX_DAILY_LOSS = .03
STOP_LOSS = .08
TAKE_PROFIT = .16
TRAILING_STOP = .10
ONE_WAY_COST = .01


def get_json(url):
    response = requests.get(url, timeout=12, headers={'User-Agent': 'MemeCoinPaperTrader/1.2'})
    response.raise_for_status()
    return response.json()


def number(value, default=0.0):
    try:
        v = float(value)
        return v if v == v and abs(v) != float('inf') else default
    except (ValueError, TypeError):
        return default


def extract(pair):
    base = pair.get('baseToken') or {}
    address = base.get('address')
    if not address:
        return None
    tx = (pair.get('txns') or {}).get('h1') or {}
    created = number(pair.get('pairCreatedAt'))
    age = max(0, (time.time() * 1000 - created) / 3600000) if created > 0 else None
    liquidity = number((pair.get('liquidity') or {}).get('usd'))
    volume = number((pair.get('volume') or {}).get('h24'))
    price = number(pair.get('priceUsd'))
    change = number((pair.get('priceChange') or {}).get('h1'))
    buys = int(number(tx.get('buys')))
    sells = int(number(tx.get('sells')))
    activity = buys + sells
    score = round(100 * (.45 * max(0, 1 - abs(change - 4) / 12) + .30 * buys / max(1, activity) + .25 * min(1, liquidity / 500000)), 1)
    reasons = []
    if price <= 0: reasons.append('missing price')
    if liquidity < 50000: reasons.append('liquidity below $50k')
    if volume < 100000: reasons.append('24h volume below $100k')
    if age is None: reasons.append('unknown pair age')
    elif not 24 <= age <= 24 * 365: reasons.append('pair age outside 1 day–1 year')
    if activity < 30: reasons.append('under 30 hourly transactions')
    return {'symbol': base.get('symbol') or '?', 'name': base.get('name') or '', 'address': address,
            'pair': pair.get('pairAddress'), 'price': price, 'liquidity': liquidity,
            'volume24h': volume, 'change1h': change, 'transactions1h': activity,
            'age_hours': round(age, 1) if age is not None else None,
            'score': score, 'eligible': not reasons, 'reasons': ', '.join(reasons), 'url': pair.get('url')}


def scan(diagnostics=False):
    """Broader search, with all discovered tokens shown separately from eligible ones."""
    selected = {}
    searches = []
    raw = 0
    solana = 0
    for term in SEEDS:
        row = {'term': term, 'status': 'ok', 'pairs': 0}
        try:
            data = get_json(f'{API}/latest/dex/search?q={quote(term)}')
            if not isinstance(data, dict):
                raise ValueError('unexpected API payload')
            pairs = data.get('pairs') or []
            row['pairs'] = len(pairs)
            raw += len(pairs)
            for p in pairs:
                if not isinstance(p, dict) or p.get('chainId') != 'solana':
                    continue
                solana += 1
                addr = (p.get('baseToken') or {}).get('address')
                if not addr: continue
                if addr not in selected or number((p.get('liquidity') or {}).get('usd')) > number((selected[addr].get('liquidity') or {}).get('usd')):
                    selected[addr] = p
        except (requests.RequestException, ValueError, TypeError) as exc:
            row['status'] = f'{type(exc).__name__}: {exc}'
        searches.append(row)
    tokens = []
    for pair in selected.values():
        try:
            t = extract(pair)
            if t: tokens.append(t)
        except (ValueError, TypeError, KeyError, OverflowError):
            pass
    tokens.sort(key=lambda t: (t['eligible'], t['score']), reverse=True)
    eligible = [t for t in tokens if t['eligible']]
    counts = Counter(reason for t in tokens for reason in t['reasons'].split(', ') if reason)
    stats = {'searches': searches, 'raw_pairs': raw, 'solana_pairs': solana,
             'unique_tokens': len(tokens), 'qualified': len(eligible), 'rejections': dict(counts)}
    return (tokens, stats) if diagnostics else eligible


def default_state():
    return {'cash': STARTING_CASH, 'positions': {}, 'trades': [], 'equity_history': [], 'day_start': {}}


def load():
    if not STATE.exists(): return default_state()
    try:
        data = json.loads(STATE.read_text())
        if not isinstance(data, dict): raise ValueError('bad state')
        return data
    except (OSError, ValueError, json.JSONDecodeError):
        raise RuntimeError('State file is damaged; do not trade until restored or explicitly reset.')


def save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(state, indent=2))
    temp.replace(STATE)


def refresh_positions(state):
    """Fetch independent prices for held tokens, even if discovery filters reject them."""
    quotes = {}
    errors = []
    for address in state['positions']:
        try:
            data = get_json(f'{API}/token-pairs/v1/solana/{quote(address)}')
            pairs = [p for p in data if isinstance(p, dict) and p.get('chainId') == 'solana' and number(p.get('priceUsd')) > 0] if isinstance(data, list) else []
            if not pairs:
                errors.append(f'{address[:8]}: no valid quote')
                continue
            best = max(pairs, key=lambda p: number((p.get('liquidity') or {}).get('usd')))
            quotes[address] = number(best['priceUsd'])
        except (requests.RequestException, ValueError, TypeError) as exc:
            errors.append(f'{address[:8]}: {type(exc).__name__}')
    return quotes, errors


def equity(state, quotes):
    return state['cash'] + sum(p['units'] * quotes.get(addr, p['last_price']) for addr, p in state['positions'].items())


def step(state, tokens, quotes=None):
    """One explicitly triggered paper cycle. Returns state; no exchange integration."""
    quotes = quotes or {}
    now = datetime.now(timezone.utc).isoformat()
    today = now[:10]
    for addr, p in list(state['positions'].items()):
        price = quotes.get(addr)
        if not price or price <= 0: continue  # never pretend stale prices are executable
        p['last_price'] = price
        p['peak_price'] = max(p.get('peak_price', p['entry_price']), price)
        if price <= p['entry_price'] * (1 - STOP_LOSS): reason = 'stop loss'
        elif price >= p['entry_price'] * (1 + TAKE_PROFIT): reason = 'take profit'
        elif price <= p['peak_price'] * (1 - TRAILING_STOP): reason = 'trailing stop'
        else: continue
        proceeds = p['units'] * price * (1 - ONE_WAY_COST)
        state['cash'] += proceeds
        state['trades'].append({'time': now, 'side': 'SELL', 'symbol': p['symbol'], 'address': addr,
                                'price': price, 'value': round(proceeds, 2), 'pnl': round(proceeds - p['cost'], 2), 'reason': reason})
        del state['positions'][addr]
    total = equity(state, quotes)
    state['day_start'].setdefault(today, total)
    # Only permit new buys if equity has not fallen to the daily loss floor.
    if total > state['day_start'][today] * (1 - MAX_DAILY_LOSS):
        for t in tokens:
            if len(state['positions']) >= MAX_OPEN_POSITIONS: break
            if not t.get('eligible') or t['score'] < 70 or t['address'] in state['positions'] or t['price'] <= 0: continue
            allocation = min(total * MAX_POSITION_FRACTION, state['cash'])
            if allocation < 10: break
            units = allocation * (1 - ONE_WAY_COST) / t['price']
            state['cash'] -= allocation
            state['positions'][t['address']] = {'symbol': t['symbol'], 'units': units, 'cost': allocation,
                 'entry_price': t['price'], 'last_price': t['price'], 'peak_price': t['price'], 'entered': now}
            state['trades'].append({'time': now, 'side': 'BUY', 'symbol': t['symbol'], 'address': t['address'],
                                   'price': t['price'], 'value': round(allocation, 2), 'pnl': None, 'reason': 'score >= 70'})
    state['equity_history'].append({'time': now, 'equity': round(equity(state, quotes), 2)})
    state['equity_history'] = state['equity_history'][-10000:]
    return state


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if not args.once:
        parser.error('Only --once is supported; continuous scheduling requires a durable worker/database.')
    tokens, stats = scan(diagnostics=True)
    state = load()
    quotes, errors = refresh_positions(state)
    step(state, [t for t in tokens if t['eligible']], quotes)
    save(state)
    print({'discovered': stats['unique_tokens'], 'qualified': stats['qualified'], 'quotes_errors': errors, 'cash': state['cash']})
