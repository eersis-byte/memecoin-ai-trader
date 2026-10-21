"""MemeCoin AI Trader 1.3: transparent, manual paper-trading diagnostics."""
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from trader import load, save, scan, step, refresh_positions, STARTING_CASH

st.set_page_config(page_title='MemeCoin AI Trader — Paper', layout='wide')
st.title('MemeCoin AI Trader 1.3')
st.caption('PAPER TRADING ONLY · Rule-based prototype · No wallet or real-money orders')
st.warning('This public demo uses temporary server-local paper state. It may reset on restart and is shared by visitors. Do not use it for verified performance records.')

if 'last_cycle' not in st.session_state:
    st.session_state.last_cycle = None

st.subheader('Paper trading controls')
if st.button('Run one paper trading cycle', type='primary'):
    report = {'time': datetime.now(timezone.utc).isoformat(), 'status': 'started', 'message': '',
              'discovered': 0, 'eligible': 0, 'score_70': 0, 'buys': 0, 'sells': 0}
    try:
        with st.spinner('Scanning tokens and checking held-position prices...'):
            tokens, stats = scan(diagnostics=True)
            report['discovered'] = stats['unique_tokens']
            report['eligible'] = stats['qualified']
            qualified = [t for t in tokens if t['eligible']]
            report['score_70'] = sum(t['score'] >= 70 for t in qualified)
            st.session_state['tokens'] = tokens
            st.session_state['stats'] = stats
            failures = [s for s in stats['searches'] if s['status'] != 'ok']
            if failures or stats['raw_pairs'] == 0:
                report['status'] = 'cancelled'
                report['message'] = 'At least one market search failed or all returned zero pairs. No simulated trades were made.'
            else:
                state = load()
                quotes, quote_errors = refresh_positions(state)
                before = len(state['trades'])
                step(state, qualified, quotes)
                save(state)
                new_trades = state['trades'][before:]
                report['buys'] = sum(t['side'] == 'BUY' for t in new_trades)
                report['sells'] = sum(t['side'] == 'SELL' for t in new_trades)
                report['status'] = 'completed'
                if new_trades:
                    report['message'] = f"Completed: {report['buys']} simulated buys and {report['sells']} simulated sells."
                elif not qualified:
                    report['message'] = 'Completed without trades: no discovered token passed the eligibility filters.'
                elif report['score_70'] == 0:
                    report['message'] = 'Completed without trades: eligible tokens scored below the buy threshold of 70.'
                else:
                    report['message'] = 'Completed without trades: tokens may already be held, position limits or the daily loss limit may block new buys; existing positions did not reach exit thresholds.'
                if quote_errors:
                    report['message'] += ' Some held-position quotes were unavailable: ' + '; '.join(quote_errors)
    except Exception as exc:
        report['status'] = 'failed'
        report['message'] = f'{type(exc).__name__}: {exc}'
    st.session_state.last_cycle = report

report = st.session_state.last_cycle
if report:
    st.subheader('Last cycle result')
    st.caption('Time (UTC): ' + report['time'])
    if report['status'] == 'completed':
        st.success(report['message'])
    elif report['status'] == 'cancelled':
        st.warning(report['message'])
    else:
        st.error(report['message'])
    a,b,c,d = st.columns(4)
    a.metric('Discovered', report['discovered'])
    b.metric('Eligible', report['eligible'])
    c.metric('Score ≥ 70', report['score_70'])
    d.metric('New paper trades', report['buys'] + report['sells'])
else:
    st.info('No trading cycle run in this browser session. Click the button above to run one.')

try:
    state = load()
except Exception as exc:
    st.error(f'Cannot load paper account: {type(exc).__name__}: {exc}')
    st.stop()

st.subheader('Paper account')
last_equity = state['equity_history'][-1]['equity'] if state['equity_history'] else STARTING_CASH
c1,c2,c3 = st.columns(3)
c1.metric('Last recorded simulated equity', f'${last_equity:,.2f}', f'{last_equity - STARTING_CASH:+,.2f} USD')
c2.metric('Cash', f"${state['cash']:,.2f}")
c3.metric('Open positions', len(state['positions']))
if state['equity_history']:
    history = pd.DataFrame(state['equity_history'])
    history['time'] = pd.to_datetime(history['time'], utc=True)
    st.line_chart(history.set_index('time')['equity'])
st.subheader('Open positions')
st.dataframe(pd.DataFrame([{'token': p['symbol'], 'address': a, 'units': p['units'], 'entry': p['entry_price'], 'last observed price': p['last_price']} for a,p in state['positions'].items()]), width='stretch')
st.subheader('Trade log')
st.dataframe(pd.DataFrame(state['trades'][::-1]), width='stretch')

st.subheader('Discovery scanner')
if st.button('Fetch current candidates'):
    with st.spinner('Querying DexScreener...'):
        try:
            tokens, stats = scan(diagnostics=True)
            st.session_state['tokens'] = tokens
            st.session_state['stats'] = stats
            st.session_state['scan_error'] = None
        except Exception as exc:
            st.session_state['scan_error'] = f'{type(exc).__name__}: {exc}'
if st.session_state.get('scan_error'):
    st.error(st.session_state['scan_error'])
if 'stats' in st.session_state:
    stats = st.session_state['stats']
    a,b,c = st.columns(3)
    a.metric('API pairs returned', stats['raw_pairs'])
    b.metric('Unique Solana tokens', stats['unique_tokens'])
    c.metric('Eligible candidates', stats['qualified'])
    st.write('Search results')
    st.dataframe(pd.DataFrame(stats['searches']), width='stretch')
    if stats['rejections']:
        st.write('Rejection reasons (tokens may fail more than one rule)')
        st.dataframe(pd.DataFrame([{'reason':k,'count':v} for k,v in stats['rejections'].items()]), width='stretch')
    st.write('Discovered tokens (including ineligible)')
    st.dataframe(pd.DataFrame(st.session_state.get('tokens', [])), width='stretch')
st.info('The score is a heuristic, not a trained AI model. Simulated fills, fees and slippage may be optimistic; results do not establish profitability.')
