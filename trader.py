"""Solana meme token research and manual paper simulator. No wallet or orders."""
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
SEEDS = ['BONK','WIF','POPCAT','FARTCOIN','PENGU','MEW','BOME','MOODENG','GOAT','PNUT','MICHI','MOG','TURBO','NEIRO','GIGA','RETARDIO','PONKE','FWOG']
STARTING_CASH = 1000.0
MAX_POSITION_FRACTION = 0.05
MAX_OPEN_POSITIONS = 4
MAX_DAILY_LOSS = 0.03
STOP_LOSS = 0.08
TAKE_PROFIT = 0.16
TRAILING_STOP = 0.10
ONE_WAY_COST = 0.01
PROFILES = {
 'Conservative': {'liquidity':50000,'volume':100000,'transactions':30,'min_age':24,'max_age':8760,'min_score':70},
 'Exploratory paper': {'liquidity':25000,'volume':25000,'transactions':10,'min_age':6,'max_age':17520,'min_score':65},
}


def number(value, default=0.0):
    try:
        v = float(value)
        return v if v == v and abs(v) != float('inf') else default
    except (TypeError, ValueError):
        return default


def get_json(url):
    r = requests.get(url, timeout=12, headers={'User-Agent':'MemeCoinPaperTrader/1.4'})
    r.raise_for_status()
    return r.json()


def extract(p):
    base = p.get('baseToken') or {}
    addr = base.get('address')
    if not addr: return None
    tx = (p.get('txns') or {}).get('h1') or {}
    created = number(p.get('pairCreatedAt'))
    age = max(0,(time.time()*1000-created)/3600000) if created>0 else None
    liquidity = number((p.get('liquidity') or {}).get('usd'))
    volume = number((p.get('volume') or {}).get('h24'))
    price = number(p.get('priceUsd'))
    change = number((p.get('priceChange') or {}).get('h1'))
    buys = max(0,int(number(tx.get('buys'))))
    sells = max(0,int(number(tx.get('sells'))))
    activity = buys+sells
    score = round(100*(.45*max(0,1-abs(change-4)/12)+.30*buys/max(1,activity)+.25*min(1,liquidity/500000)),1)
    return {'symbol':base.get('symbol') or '?','name':base.get('name') or '', 'address':addr,
            'pair':p.get('pairAddress'),'price':price,'liquidity':liquidity,'volume24h':volume,
            'change1h':change,'transactions1h':activity,'age_hours':round(age,1) if age is not None else None,
            'score':score,'url':p.get('url')}


def evaluate(token, profile='Conservative'):
    limits=PROFILES[profile]
    reasons=[]
    if token['price']<=0: reasons.append('Missing valid USD price')
    if token['liquidity']<limits['liquidity']: reasons.append('Insufficient liquidity')
    if token['volume24h']<limits['volume']: reasons.append('Insufficient 24h volume')
    age=token['age_hours']
    if age is None: reasons.append('Unknown pair age')
    elif not limits['min_age']<=age<=limits['max_age']: reasons.append('Outside pair age range')
    if token['transactions1h']<limits['transactions']: reasons.append('Insufficient hourly transactions')
    return reasons


def scan(profile='Conservative', diagnostics=False):
    if profile not in PROFILES: raise ValueError('Unknown profile')
    selected={}; searches=[]; raw=0; solana=0
    for term in SEEDS:
        row={'term':term,'status':'ok','pairs':0}
        try:
            data=get_json(f'{API}/latest/dex/search?q={quote(term)}')
            if not isinstance(data,dict): raise ValueError('Unexpected search response')
            pairs=data.get('pairs') or []
            if not isinstance(pairs,list): raise ValueError('Invalid pairs data')
            row['pairs']=len(pairs);raw+=len(pairs)
            for p in pairs:
                if not isinstance(p,dict) or p.get('chainId')!='solana':continue
                solana+=1
                addr=(p.get('baseToken') or {}).get('address')
                if not addr:continue
                # Prefer the most liquid pair with a valid price, to avoid dead pools.
                rank=(number(p.get('priceUsd'))>0,number((p.get('liquidity') or {}).get('usd')))
                old=selected.get(addr)
                if old is None or rank>(number(old.get('priceUsd'))>0,number((old.get('liquidity') or {}).get('usd'))):selected[addr]=p
        except (requests.RequestException,ValueError,TypeError) as exc:
            row['status']=f'{type(exc).__name__}: {exc}'
        searches.append(row)
    tokens=[]
    for p in selected.values():
        try:
            t=extract(p)
            if t:
                reasons=evaluate(t,profile)
                t.update({'eligible':not reasons,'reasons':'; '.join(reasons),
                          'risk_flags':'Automated honeypot/rug checks NOT implemented'})
                tokens.append(t)
        except (TypeError,ValueError,KeyError,OverflowError):pass
    tokens.sort(key=lambda t:(t['eligible'],t['score']),reverse=True)
    counts=Counter(reason for t in tokens for reason in t['reasons'].split('; ') if reason)
    stats={'searches':searches,'raw_pairs':raw,'solana_pairs':solana,'unique_tokens':len(tokens),
           'qualified':sum(t['eligible'] for t in tokens),'rejections':dict(counts),'profile':profile,
           'searched_at':datetime.now(timezone.utc).isoformat()}
    return (tokens,stats) if diagnostics else [t for t in tokens if t['eligible']]


def default_state():
    return {'cash':STARTING_CASH,'positions':{},'trades':[],'equity_history':[],'day_start':{},'last_cycle':None}


def load():
    if not STATE.exists():return default_state()
    try:
        data=json.loads(STATE.read_text())
        if not isinstance(data,dict) or not all(k in data for k in ('cash','positions','trades','equity_history','day_start')):raise ValueError('invalid schema')
        return data
    except (OSError,ValueError) as exc:raise RuntimeError('Paper state damaged; restore a backup rather than overwriting it') from exc


def save(state):
    STATE.parent.mkdir(parents=True,exist_ok=True)
    temp=STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(state,indent=2))
    temp.replace(STATE)


def refresh_positions(state):
    quotes={};errors=[]
    for address in state['positions']:
        try:
            data=get_json(f'{API}/token-pairs/v1/solana/{quote(address)}')
            pairs=[p for p in data if isinstance(p,dict) and p.get('chainId')=='solana' and number(p.get('priceUsd'))>0] if isinstance(data,list) else []
            if not pairs:
                errors.append(f'{address[:8]}: no valid quote');continue
            best=max(pairs,key=lambda p:number((p.get('liquidity') or {}).get('usd')))
            quotes[address]=number(best['priceUsd'])
        except (requests.RequestException,ValueError,TypeError) as exc:errors.append(f'{address[:8]}: {type(exc).__name__}')
    return quotes,errors


def equity(state,quotes):
    return state['cash']+sum(p['units']*quotes.get(a,p['last_price']) for a,p in state['positions'].items())


def step(state,tokens,quotes=None,min_score=70):
    quotes=quotes or {};now=datetime.now(timezone.utc).isoformat();today=now[:10]
    for addr,p in list(state['positions'].items()):
        price=quotes.get(addr)
        if not price or price<=0:continue
        p['last_price']=price;p['peak_price']=max(p.get('peak_price',p['entry_price']),price)
        if price<=p['entry_price']*(1-STOP_LOSS):reason='stop loss'
        elif price>=p['entry_price']*(1+TAKE_PROFIT):reason='take profit'
        elif price<=p['peak_price']*(1-TRAILING_STOP):reason='trailing stop'
        else:continue
        proceeds=p['units']*price*(1-ONE_WAY_COST)
        state['cash']+=proceeds
        state['trades'].append({'time':now,'side':'SELL','symbol':p['symbol'],'address':addr,
          'price':price,'value':round(proceeds,2),'pnl':round(proceeds-p['cost'],2),'reason':reason})
        del state['positions'][addr]
    total=equity(state,quotes)
    state['day_start'].setdefault(today,total)
    if total>state['day_start'][today]*(1-MAX_DAILY_LOSS):
        for t in tokens:
            if len(state['positions'])>=MAX_OPEN_POSITIONS:break
            if not t.get('eligible') or t['score']<min_score or t['address'] in state['positions'] or t['price']<=0:continue
            allocation=min(total*MAX_POSITION_FRACTION,state['cash'])
            if allocation<10:break
            units=allocation*(1-ONE_WAY_COST)/t['price']
            state['cash']-=allocation
            state['positions'][t['address']]={'symbol':t['symbol'],'units':units,'cost':allocation,
                'entry_price':t['price'],'last_price':t['price'],'peak_price':t['price'],'entered':now}
            state['trades'].append({'time':now,'side':'BUY','symbol':t['symbol'],'address':t['address'],
                'price':t['price'],'value':round(allocation,2),'pnl':None,'reason':f'score >= {min_score}'})
    state['equity_history'].append({'time':now,'equity':round(equity(state,quotes),2)})
    state['equity_history']=state['equity_history'][-10000:]
    return state


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--profile',choices=PROFILES,default='Conservative')
    args=parser.parse_args()
    if not args.once:parser.error('Only --once is supported. No unattended execution.')
    tokens,stats=scan(args.profile,True)
    state=load();quotes,errors=refresh_positions(state)
    if any(s['status']!='ok' for s in stats['searches']) or not stats['raw_pairs'] or errors:
        print({'status':'cancelled','reason':'missing market data','stats':stats['unique_tokens'],'quote_errors':errors})
    else:
        step(state,[t for t in tokens if t['eligible']],quotes,PROFILES[args.profile]['min_score'])
        save(state)
        print({'status':'completed','discovered':stats['unique_tokens'],'eligible':stats['qualified']})
