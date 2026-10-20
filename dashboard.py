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
st.dataframe(pd.DataFrame([{'token': p['symbol'], 'address': a, 'units': p['units'], 'entry': p['entry_price'], 'last observed price': p['last_price']} for a, p in state['positions'].items()]), use_container_width=True)
st.subheader('Trade log')
st.dataframe(pd.DataFrame(state['trades'][::-1]), use_container_width=True)
st.subheader('Discovery scanner')
if st.button('Fetch current candidates'):
    with st.spinner('Querying DexScreener...'):
        st.dataframe(pd.DataFrame(scan()), use_container_width=True)
st.info('Prices are polled snapshots. The scanner is limited to seed searches; missing/stale quotes and unmodeled liquidity impact make performance estimates optimistic. The score is a heuristic, not trained AI. Do not fund a wallet based on this prototype.')
