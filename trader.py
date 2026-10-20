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


def scan():
    """Search a limited discovery universe; not a complete new-token feed."""
    pairs = {}
    for symbol in SEEDS:
        try:
            payload = get_json(f'{API}/latest/dex/search?q={symbol}')
            for p in payload.get('pairs') or []:
                if p.get('chainId') != 'solana':
                    continue
                key = p.get('baseToken', {}).get('address')
                if not key or key in pairs:
                    continue
                pairs[key] = p
        except (requests.RequestException, ValueError) as exc:
            print(f'Warning: search for {symbol} failed: {exc}')
    results = []
    for p in pairs.values():
        try:
            liquidity = float((p.get('liquidity') or {}).get('usd') or 0)
            volume = float((p.get('volume') or {}).get('h24') or 0)
            change = float((p.get('priceChange') or {}).get('h1') or 0)
            price = float(p.get('priceUsd') or 0)
            buys = int(((p.get('txns') or {}).get('h1') or {}).get('buys') or 0)
            sells = int(((p.get('txns') or {}).get('h1') or {}).get('sells') or 0)
            age_hours = (time.time() * 1000 - int(p.get('pairCreatedAt') or 0)) / 3_600_000
            if not (price > 0 and liquidity >= 50000 and volume >= 100000 and 24 <= age_hours <= 24 * 365 and buys + sells >= 30):
                continue
            # Heuristic score, not an ML prediction. Avoid chasing extreme one-hour pumps.
            momentum = max(0, 1 - abs(change - 4) / 12)
            activity = buys / max(1, buys + sells)
            liquidity_score = min(1, liquidity / 500000)
            score = round(100 * (0.45 * momentum + 0.30 * activity + 0.25 * liquidity_score), 1)
            results.append({'symbol': p['baseToken']['symbol'], 'name': p['baseToken']['name'],
                            'address': p['baseToken']['address'], 'pair': p['pairAddress'],
                            'price': price, 'liquidity': liquidity, 'volume24h': volume,
                            'change1h': change, 'score': score, 'url': p.get('url')})
        except (TypeError, ValueError, KeyError):
            continue
    return sorted(results, key=lambda x: x['score'], reverse=True)


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
