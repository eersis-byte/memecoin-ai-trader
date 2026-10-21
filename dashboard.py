"""MemeCoin AI Trader 1.4 — research dashboard and manual paper cycles."""
import json
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from trader import (load, save, scan, step, refresh_positions, PROFILES,
                    STARTING_CASH)

st.set_page_config(page_title='MemeCoin AI Trader — Paper',layout='wide')
st.title('MemeCoin AI Trader 1.4')
st.caption('RESEARCH + PAPER TRADING ONLY · No wallet, exchange access or real-money orders')
st.warning('Public demo: server-local paper state can reset on redeployment and may be shared by visitors. Export backups. This is NOT durable or private storage.')
st.error('Meme coins can be scams or illiquid. Token safety checks (honeypot, freeze/mint authorities, holder concentration) are NOT implemented. A score is not a safety rating.')

profile=st.selectbox('Paper-trading eligibility profile',list(PROFILES),index=0,
    help='Exploratory relaxes minimums for research and simulated trades ONLY. It does not make tokens safe.')
limits=PROFILES[profile]
st.caption(f"{profile}: liquidity ≥ ${limits['liquidity']:,}, 24h volume ≥ ${limits['volume']:,}, hourly trades ≥ {limits['transactions']}, age {limits['min_age']}–{limits['max_age']} hours, score ≥ {limits['min_score']}")

try:state=load()
except Exception as exc:
    st.error(f'Unable to load paper state: {type(exc).__name__}: {exc}')
    st.stop()

st.subheader('Paper trading controls')
if st.button('Run one paper trading cycle',type='primary'):
    report={'time':datetime.now(timezone.utc).isoformat(),'profile':profile,'status':'started',
            'message':'','discovered':0,'eligible':0,'above_score':0,'buys':0,'sells':0}
    try:
        with st.spinner('Scanning market data and refreshing held positions...'):
            tokens,stats=scan(profile,diagnostics=True)
            st.session_state['tokens']=tokens
            st.session_state['stats']=stats
            report['discovered']=stats['unique_tokens'];report['eligible']=stats['qualified']
            qualified=[t for t in tokens if t['eligible']]
            report['above_score']=sum(t['score']>=limits['min_score'] for t in qualified)
            quotes,quote_errors=refresh_positions(state)
            failed=[s for s in stats['searches'] if s['status']!='ok']
            if failed or stats['raw_pairs']==0 or quote_errors:
                report['status']='cancelled'
                report['message']='Market search or held-position price data was incomplete. No paper cycle executed. '+ '; '.join(quote_errors)
            else:
                before=len(state['trades'])
                step(state,qualified,quotes,limits['min_score'])
                recent=state['trades'][before:]
                report['buys']=sum(t['side']=='BUY' for t in recent)
                report['sells']=sum(t['side']=='SELL' for t in recent)
                report['status']='completed'
                if recent:report['message']=f"Simulated {report['buys']} buys and {report['sells']} sells."
                elif not qualified:report['message']='No tokens met the selected eligibility requirements.'
                elif not report['above_score']:report['message']='No eligible tokens reached the minimum score.'
                else:report['message']='No new trades: existing positions, allocation limits, or daily loss controls may apply.'
                state['last_cycle']=report
                save(state)
    except Exception as exc:
        report['status']='failed';report['message']=f'{type(exc).__name__}: {exc}'
    st.session_state['last_cycle']=report

report=st.session_state.get('last_cycle') or state.get('last_cycle')
if report:
    st.subheader('Last cycle result')
    st.caption(f"{report['time']} UTC · {report['profile']} · {report['status']}")
    if report['status']=='completed':st.success(report['message'])
    elif report['status']=='cancelled':st.warning(report['message'])
    else:st.error(report['message'])
    cols=st.columns(4)
    for col,label,key in zip(cols,['Discovered','Eligible','At/above score','New paper trades'],
                             ['discovered','eligible','above_score','buys']):
        value=report.get(key,0)+(report.get('sells',0) if key=='buys' else 0)
        col.metric(label,value)
else:st.info('No paper cycle recorded. Select a profile and click Run one paper trading cycle.')

# Reload so displayed account reflects a completed cycle.
state=load()
st.subheader('Paper account')
last=state['equity_history'][-1]['equity'] if state['equity_history'] else STARTING_CASH
c1,c2,c3=st.columns(3)
c1.metric('Last recorded simulated equity',f'${last:,.2f}',f'{last-STARTING_CASH:+,.2f} USD')
c2.metric('Cash',f"${state['cash']:,.2f}")
c3.metric('Open positions',len(state['positions']))
if state['equity_history']:
    h=pd.DataFrame(state['equity_history']);h['time']=pd.to_datetime(h['time'],utc=True)
    st.line_chart(h.set_index('time')['equity'])
st.subheader('Open positions')
st.dataframe(pd.DataFrame([{'symbol':p['symbol'],'address':a,'units':p['units'],
    'entry_price':p['entry_price'],'last_observed_price':p['last_price']} for a,p in state['positions'].items()]),width='stretch')
st.subheader('Trade log')
st.dataframe(pd.DataFrame(state['trades'][::-1]),width='stretch')
st.download_button('Download paper account backup (JSON)',data=json.dumps(state,indent=2),
                   file_name='memecoin_paper_backup.json',mime='application/json')
st.caption('Backup contains paper trades only. Keep it private. This is a manual export, not an automatic backup.')

st.subheader('Discovery scanner')
if st.button('Fetch current candidates'):
    with st.spinner('Querying DexScreener...'):
        try:
            tokens,stats=scan(profile,diagnostics=True)
            st.session_state.update(tokens=tokens,stats=stats,scan_error=None,scan_profile=profile)
        except Exception as exc:st.session_state['scan_error']=f'{type(exc).__name__}: {exc}'
if st.session_state.get('scan_error'):st.error(st.session_state['scan_error'])
if 'stats' in st.session_state:
    stats=st.session_state['stats']
    st.caption(f"Scan profile: {stats['profile']} · UTC: {stats['searched_at']}. Refresh after changing profile.")
    a,b,c=st.columns(3)
    a.metric('API pairs returned',stats['raw_pairs'])
    b.metric('Unique Solana tokens',stats['unique_tokens'])
    c.metric('Eligible candidates',stats['qualified'])
    with st.expander('Search requests and errors',expanded=False):
        st.dataframe(pd.DataFrame(stats['searches']),width='stretch')
    with st.expander('Reasons tokens failed eligibility',expanded=True):
        st.dataframe(pd.DataFrame([{'reason':k,'tokens':v} for k,v in stats['rejections'].items()]),width='stretch')
    st.write('Discovered tokens (including ineligible)')
    st.dataframe(pd.DataFrame(st.session_state['tokens']),width='stretch',hide_index=True)
    st.download_button('Download scan results (CSV)',data=pd.DataFrame(st.session_state['tokens']).to_csv(index=False),
                       file_name='memecoin_scan.csv',mime='text/csv')
st.info('Search-based discovery is incomplete and may contain spoofed token names. Paper fills use price snapshots and estimated 1% costs per side, not actual executable quotes. This prototype cannot establish profitable trading.')
