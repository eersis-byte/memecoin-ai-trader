import pandas as pd
import streamlit as st
from trader import load, scan

st.set_page_config(page_title='MemeCoin AI Trader — Paper', layout='wide')
st.title('MemeCoin AI Trader 1.0')
st.caption('PAPER TRADING ONLY · Educational prototype · No real-money orders')

state = load()
last_equity = state['equity_history'][-1]['equity'] if state['equity_history'] else 1000
c1, c2, c3 = st.columns(3)
c1.metric('Simulated equity', f'${last_equity:,.2f}', f'{last_equity - 1000:+,.2f} USD')
c2.metric('Cash', f"${state['cash']:,.2f}")
c3.metric('Open positions', len(state['positions']))

if state['equity_history']:
    history = pd.DataFrame(state['equity_history'])
    history['time'] = pd.to_datetime(history['time'])
    st.line_chart(history.set_index('time')['equity'])

st.subheader('Open positions')
st.dataframe(pd.DataFrame([
    {'token': p['symbol'], 'address': a, 'units': p['units'],
     'entry': p['entry_price'], 'last observed price': p['last_price']}
    for a, p in state['positions'].items()
]), width='stretch')

st.subheader('Trade log')
st.dataframe(pd.DataFrame(state['trades'][::-1]), width='stretch')

st.subheader('Discovery scanner')
if st.button('Fetch current candidates'):
    with st.spinner('Querying DexScreener...'):
        try:
            st.session_state['scan_results'] = scan()
            st.session_state['scan_error'] = None
        except Exception as exc:
            st.session_state['scan_results'] = None
            st.session_state['scan_error'] = f'{type(exc).__name__}: {exc}'

if st.session_state.get('scan_error'):
    st.error('Scanner failed: ' + st.session_state['scan_error'])
elif 'scan_results' in st.session_state:
    results = st.session_state['scan_results']
    st.metric('Qualified candidates', len(results))
    if results:
        st.dataframe(pd.DataFrame(results), width='stretch')
    else:
        st.warning('No coins qualified. This can mean DexScreener returned no pairs, requests failed, or all pairs were excluded by trader.py filters. Check Streamlit app logs for "Warning: search" messages.')

st.info('Prices are polled snapshots. The scanner is limited to seed searches; missing/stale quotes and unmodeled liquidity impact make performance estimates optimistic. The score is a heuristic, not trained AI. Do not fund a wallet based on this prototype.')
