import pandas as pd
import streamlit as st
from trader import load, save, scan, step, refresh_positions, equity, STARTING_CASH

st.set_page_config(page_title='MemeCoin AI Trader — Paper', layout='wide')
st.title('MemeCoin AI Trader 1.2')
st.caption('PAPER TRADING ONLY · Rule-based prototype · No wallet or real-money orders')
st.warning('Streamlit Community Cloud local state is temporary and may reset on restart. Do not treat this as a reliable long-term trading record.')

try:
    state = load()
except Exception as exc:
    st.error(f'Cannot load paper account: {exc}')
    st.stop()

last_equity = state['equity_history'][-1]['equity'] if state['equity_history'] else STARTING_CASH
c1, c2, c3 = st.columns(3)
c1.metric('Last recorded simulated equity', f'${last_equity:,.2f}', f'{last_equity-STARTING_CASH:+,.2f} USD')
c2.metric('Cash', f"${state['cash']:,.2f}")
c3.metric('Open positions', len(state['positions']))
if state['equity_history']:
    history = pd.DataFrame(state['equity_history'])
    history['time'] = pd.to_datetime(history['time'], utc=True)
    st.line_chart(history.set_index('time')['equity'])
st.subheader('Open positions')
st.dataframe(pd.DataFrame([{'token': p['symbol'], 'address': a, 'units': p['units'],
   'entry': p['entry_price'], 'last observed price': p['last_price']} for a,p in state['positions'].items()]), width='stretch')
st.subheader('Trade log')
st.dataframe(pd.DataFrame(state['trades'][::-1]), width='stretch')

st.subheader('Discovery scanner')
st.caption('Discovery includes ineligible coins for research. Only eligible coins scoring 70+ may be purchased in a paper cycle.')
if st.button('Fetch current candidates', type='primary'):
    with st.spinner('Searching DexScreener...'):
        try:
            tokens, stats = scan(diagnostics=True)
            st.session_state['tokens'] = tokens
            st.session_state['stats'] = stats
            st.session_state['error'] = None
        except Exception as exc:
            st.session_state['error'] = f'{type(exc).__name__}: {exc}'
if st.session_state.get('error'):
    st.error(st.session_state['error'])
if 'stats' in st.session_state:
    stats = st.session_state['stats']
    a,b,c = st.columns(3)
    a.metric('API pairs returned', stats['raw_pairs'])
    b.metric('Unique Solana tokens', stats['unique_tokens'])
    c.metric('Eligible candidates', stats['qualified'])
    st.write('API searches')
    st.dataframe(pd.DataFrame(stats['searches']), width='stretch')
    if stats['rejections']:
        st.write('Rejection counts (a token may fail multiple checks)')
        st.dataframe(pd.DataFrame([{'reason':k,'count':v} for k,v in stats['rejections'].items()]), width='stretch')
    st.write('Discovered tokens — eligible and ineligible')
    tokens = st.session_state.get('tokens', [])
    if tokens:
        st.dataframe(pd.DataFrame(tokens), width='stretch')
    else:
        st.warning('No tokens discovered. Check API search statuses.')

st.subheader('Paper trading')
st.caption('Runs exactly one simulated cycle when clicked. It does not run in the background.')
if st.button('Run one paper trading cycle'):
    with st.spinner('Scanning candidates and independently refreshing held-token prices...'):
        try:
            tokens, stats = scan(diagnostics=True)  # fresh snapshot; do not trade stale session results
            failures = [s for s in stats['searches'] if s['status'] != 'ok']
            if failures or stats['raw_pairs'] == 0:
                st.error('Searches failed or returned no pairs; cycle cancelled to avoid acting on incomplete data.')
            else:
                quotes, errors = refresh_positions(state)
                if errors:
                    st.warning('Some held-token quotes were unavailable; those positions will not be sold on stale prices: ' + '; '.join(errors))
                before = len(state['trades'])
                step(state, [t for t in tokens if t['eligible']], quotes)
                save(state)
                st.success(f'Paper cycle recorded. New simulated trades: {len(state["trades"])-before}. Refresh to view updated account.')
                st.rerun()
        except Exception as exc:
            st.error(f'Paper cycle failed: {type(exc).__name__}: {exc}')

st.info('Heuristic scores are not AI predictions. Quotes are snapshots; stops cannot guarantee exits at their thresholds. Trading costs, price impact, data gaps, and potential token fraud may be substantially worse than modeled. Never fund a wallet based on this prototype.')
