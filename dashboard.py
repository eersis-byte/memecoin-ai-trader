import pandas as pd
import streamlit as st
from trader import load, scan

st.set_page_config(page_title='MemeCoin AI Trader — Paper', layout='wide')
st.title('MemeCoin AI Trader 1.1')
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
            results, stats = scan(diagnostics=True)
            st.session_state['scan_results'] = results
            st.session_state['scan_stats'] = stats
            st.session_state['scan_error'] = None
        except Exception as exc:
            st.session_state['scan_error'] = f'{type(exc).__name__}: {exc}'

if st.session_state.get('scan_error'):
    st.error('Scanner failed: ' + st.session_state['scan_error'])
elif 'scan_stats' in st.session_state:
    stats = st.session_state['scan_stats']
    a, b, c = st.columns(3)
    a.metric('API pairs returned', stats['raw_pairs'])
    b.metric('Unique Solana tokens', stats['unique_tokens'])
    c.metric('Qualified candidates', stats['qualified'])
    st.write('Search results and errors')
    st.dataframe(pd.DataFrame(stats['searches']), width='stretch')
    if stats['rejections']:
        st.write('Why tokens were rejected (first failing rule per token)')
        st.dataframe(pd.DataFrame([{'reason': k, 'count': v}
                                   for k, v in stats['rejections'].items()]), width='stretch')
    results = st.session_state.get('scan_results', [])
    if results:
        st.dataframe(pd.DataFrame(results), width='stretch')
    else:
        st.warning('No tokens passed the existing filters. Review the diagnostics above.')

st.info('Prices are polled snapshots. The scanner is limited to seed searches; missing/stale quotes and unmodeled liquidity impact make performance estimates optimistic. The score is a heuristic, not trained AI. Do not fund a wallet based on this prototype.')
