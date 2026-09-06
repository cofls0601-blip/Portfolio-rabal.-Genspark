# app.py (파트 1 - 초기화, 페이지 설정, 공통 함수)
import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta
from pathlib import Path
import json

from data_manager import DataManager
from models import (
    StrategyConfig, RuleConfig, RuleType, RebalanceFrequency, FilterConfig,
    FilterType, FilterTrigger, BaseAsset, AssetSnapshot
)
from rules_engine import RuleEngine
from price_fetcher import PriceFetcher

# ==================== 페이지 설정 ====================
st.set_page_config(
    page_title='자산배분 리밸런싱 도우미',
    page_icon='📊',
    layout='wide',
    initial_sidebar_state='expanded'
)

# ==================== 스타일 ====================
st.markdown("""
<style>
:root {
    --sage: #8DA377;
    --sage-dark: #6E8A5B;
    --sage-tint: rgba(141, 163, 119, 0.14);
    --terracotta: #C1795A;
    --terracotta-dark: #A15E42;
    --terracotta-tint: rgba(193, 121, 90, 0.14);
    --olive: #7D7A4F;
    --olive-dark: #5F5D3C;
    --beige: #F4EFE6;
    --beige-deep: #EAE1D0;
    --ink: #4A4638;
}

.stApp { background-color: var(--beige); }
h1, h2, h3, h4 { color: var(--olive-dark) !important; }
div[data-testid="stMetricValue"] { color: var(--olive-dark) !important; }
.stButton button[kind="primary"] {
    background-color: var(--sage-dark) !important;
    border-color: var(--sage-dark) !important;
}

.action-buy {
    border-left: 4px solid #B23B2E;
    background: rgba(178, 59, 46, 0.08);
    padding: 10px 12px;
    border-radius: 6px;
    margin-bottom: 8px;
}

.action-sell {
    border-left: 4px solid #2E5F8A;
    background: rgba(46, 95, 138, 0.08);
    padding: 10px 12px;
    border-radius: 6px;
    margin-bottom: 8px;
}

.action-hold {
    border-left: 4px solid var(--beige-deep);
    background: rgba(122, 110, 80, 0.05);
    padding: 10px 12px;
    border-radius: 6px;
    margin-bottom: 8px;
}
</style>
""", unsafe_allow_html=True)

# ==================== 세션 상태 초기화 ====================
DataManager.init_db()

if 'assets_df' not in st.session_state:
    st.session_state.assets_df = pd.DataFrame()
    
if 'vdf' not in st.session_state:
    st.session_state.vdf = pd.DataFrame()

# ==================== 공통 함수 ====================
def format_currency(value: float) -> str:
    """통화 포맷"""
    return f"{value:,.0f}원"

def format_percent(value: float) -> str:
    """백분율 포맷"""
    return f"{value*100:.2f}%"

def format_number(value: float, decimals=0) -> str:
    """숫자 포맷"""
    return f"{value:,.{int(decimals)}f}"

def get_all_active_strategies() -> List[StrategyConfig]:
    """활성화된 전략만 반환"""
    return [s for s in DataManager.get_strategies() if s.active]

def calculate_prices(prices_list: List[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """종가, SMA10, 12개월 모멘텀 계산"""
    prices = [p for p in prices_list if p and p > 0]
    
    if not prices:
        return None, None, None
    
    close = prices[-1]
    sma = sum(prices[-10:]) / 10 if len(prices) >= 10 else None
    mom = (prices[-1] / prices[-13] - 1) if len(prices) >= 13 and prices[-13] else None
    
    return close, sma, mom

def get_or_create_cash_row(strategy: StrategyConfig) -> AssetSnapshot:
    """전략의 현금 행 생성/반환"""
    return AssetSnapshot(
        ticker='CASH',
        name='현금',
        strategy_code=strategy.code,
        market='KR',
        category='현금',
        shares=0.0,
        close=1.0,
        prices=[],
        role='대기현금',
        target_pct=0.0
    )

# ==================== 메인 UI ====================
st.title('📊 자산배분 리밸런싱 도우미')
st.caption('규칙 엔진 기반 · 버전 관리 · 히스토리 보호')

with st.sidebar:
    st.header('📋 메뉴')
    page = st.radio(
        '페이지 선택',
        [
            'Action Plan',
            '포트폴리오 대시보드',
            '전략 관리',
            '규칙 빌더',
            '리밸런싱 히스토리',
            '성과 분석',
            '설정'
        ],
        label_visibility='collapsed'
    )
    
    st.divider()
    st.caption('💾 자동 거래: 미지원 (수동 실행만 저장)')

# ==================== PAGE: Action Plan ====================
if page == 'Action Plan':
    st.header('Action Plan')
    st.caption('모든 활성 전략의 종가·신호 상태와 리밸런싱 액션을 한 번에 봅니다')
    
    col1, col2 = st.columns(2)
    with col1:
        run_date = st.date_input('기준일', date.today(), key='action_date')
    with col2:
        source = st.selectbox('국내 가격 소스', ['krx', 'data_go'], index=1)
    
    if st.button('📥 종가 및 신호 데이터 불러오기', type='primary'):
        with st.spinner('데이터 불러오는 중...'):
            # 가격 조회 (Yahoo 사용)
            active_strats = get_all_active_strategies()
            ok = 0
            errors = []
            
            vdf_rows = []
            
            for strat in active_strats:
                for asset in strat.rules.base_assets:
                    if asset.ticker == 'CASH':
                        vdf_rows.append({
                            '전략': strat.code,
                            '티커': 'CASH',
                            'ETF': '현금',
                            '시장': asset.market,
                            '종가': 1.0,
                            'SMA10': None,
                            '12M': None,
                            '현재금액': 0.0,
                            '목표비중': 0.0,
                            'dd': None
                        })
                        continue
                    
                    try:
                        if asset.market == 'US':
                            day_row = PriceFetcher.fetch_yahoo_day(asset.ticker, run_date.isoformat())
                            if day_row:
                                monthly_df = PriceFetcher.fetch_yahoo_monthly(asset.ticker, run_date.isoformat())
                                prices = monthly_df['close'].tolist() if not monthly_df.empty else []
                            else:
                                prices = []
                        else:
                            # 국내 종목은 나중에 KRX/공공데이터 추가
                            prices = []
                            day_row = None
                        
                        if prices:
                            close, sma, mom = calculate_prices(prices)
                        else:
                            close, sma, mom = None, None, None
                        
                        vdf_rows.append({
                            '전략': strat.code,
                            '티커': asset.ticker,
                            'ETF': asset.name,
                            '시장': asset.market,
                            '종가': close or 0.0,
                            'SMA10': sma,
                            '12M': mom,
                            '현재금액': 0.0,  # 나중에 보유수량으로 계산
                            '목표비중': asset.target_pct,
                            'dd': None
                        })
                        ok += 1
                    except Exception as e:
                        errors.append(f"{asset.ticker}: {str(e)}")
            
            st.session_state.vdf = pd.DataFrame(vdf_rows)
            
            st.success(f'✓ {ok}개 종목 데이터 불러옴')
            if errors:
                st.warning('오류: ' + ' | '.join(errors[:5]))
    
    # Action Plan 표시
    if not st.session_state.vdf.empty:
        st.subheader('액션 플랜')
        
        active_strats = get_all_active_strategies()
        
        for strat in active_strats:
            with st.expander(f'🔧 {strat.code} - {strat.account_name}', expanded=True):
                st.caption(strat.rules.description)
                
                # 규칙 엔진 실행
                engine = RuleEngine(
                    strat,
                    [],  # assets 나중에
                    st.session_state.vdf,
                    {},  # trigger_dd
                    PriceFetcher.fetch_usd_krw()
                )
                
                result = engine.evaluate(run_date)
                
                st.caption(f"📌 적용 규칙: v{strat.rules.version}")
                
                for action in result.actions:
                    amt = action.action_amount
                    action_type = action.action_type()
                    
                    if action_type == 'BUY':
                        css_class = 'action-buy'
                        action_html = f'<b style="color:#B23B2E;">+{format_currency(amt)} 매수</b>'
                    elif action_type == 'SELL':
                        css_class = 'action-sell'
                        action_html = f'<b style="color:#2E5F8A;">{format_currency(amt)} 매도</b>'
                    else:
                        css_class = 'action-hold'
                        action_html = '<b>변동 없음</b>'
                    
                    body = f'''
                    <div class="{css_class}">
                        <div style="font-weight:700; margin-bottom:4px;">{action.name}</div>
                        <div style="font-size:0.88rem; line-height:1.6;">
                            현재: {format_currency(action.current_value)} → 목표: {format_currency(action.target_value)}<br>
                            {action_html}<br>
                            {action.reason}
                        </div>
                    </div>
                    '''
                    st.markdown(body, unsafe_allow_html=True)
                
                st.divider()
                
                # 액션 요약
                buys = [a for a in result.actions if a.action_type() == 'BUY']
                sells = [a for a in result.actions if a.action_type() == 'SELL']
                
                summary_parts = []
                if buys:
                    summary_parts.append(f"매수: {', '.join(f'{a.name} {format_currency(a.action_amount)}' for a in buys)}")
                if sells:
                    summary_parts.append(f"매도: {', '.join(f'{a.name} {format_currency(-a.action_amount)}' for a in sells)}")
                
                if summary_parts:
                    st.caption('📋 요약: ' + ' | '.join(summary_parts))
                else:
                    st.caption('📋 요약: 거래 없음')
    
    st.divider()
    
    if st.button('💾 이번 액션플랜을 히스토리에 저장', type='primary'):
        snapshot_date = st.session_state.vdf.iloc[0]['날짜'] if not st.session_state.vdf.empty else run_date.isoformat()
        DataManager.save_snapshot(
            run_date,
            total_value=0.0,  # 나중에 계산
            composition=[],
            plan_text="액션플랜 자동 저장"
        )
        st.success('✓ 히스토리에 저장했습니다')

elif page == '포트폴리오 대시보드':
    st.header('포트폴리오 대시보드')
    st.caption('전략(계좌)별 구성과 자산분류별 분포')
    
    st.metric('전체 총자산 (예)', '₩0')
    st.info('자산 데이터가 아직 입력되지 않았습니다.')

elif page == '전략 관리':
    st.header('전략 관리')
    st.caption('기존 전략 조회, 활성화/비활성화, 삭제')
    
    strategies = DataManager.get_strategies()
    
    if not strategies:
        st.info('등록된 전략이 없습니다. 규칙 빌더에서 새 전략을 만들어보세요.')
    else:
        for strat in strategies:
            with st.expander(f"{strat.code} - {strat.account_name}", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    active = st.checkbox('활성화', value=strat.active, key=f'active_{strat.code}')
                    if active != strat.active:
                        strat.active = active
                        DataManager.save_strategy(strat)
                        st.rerun()
                with col2:
                    if st.button('🗑 삭제', key=f'del_{strat.code}'):
                        DataManager.delete_strategy(strat.code)
                        st.rerun()
                
                st.markdown(f"**규칙 타입**: {strat.rules.rule_type.value}")
                st.markdown(f"**버전**: {strat.rules.version}")
                st.markdown(f"**설명**: {strat.rules.description}")
                
                st.json(strat.rules.to_dict())

elif page == '규칙 빌더':
    st.header('규칙 빌더')
    st.caption('전략 규칙을 UI에서 그래픽적으로 정의합니다')
    
    tab1, tab2 = st.tabs(['새 전략 만들기', '기존 전략 수정'])
    
    with tab1:
        st.subheader('새 전략 만들기')
        
        with st.form('new_strategy_form'):
            st.markdown('#### 기본 정보')
            strat_code = st.text_input('전략 코드', placeholder='예: CORE1', max_chars=20).upper()
            account_name = st.text_input('계좌 별명', placeholder='예: 개인연금')
            
            st.markdown('#### 규칙 설정')
            rule_type = st.selectbox(
                '리밸런싱 유형',
                [
                    (RuleType.STATIC_WITH_FILTERS, '정적 + 필터 (LAA)'),
                    (RuleType.DYNAMIC_MOMENTUM, '동적 모멘텀 (GSM)'),
                    (RuleType.BUY_AND_HOLD, 'Buy & Hold (금현물)'),
                    (RuleType.CUSTOM_TRIGGER, '커스텀 트리거 (ISA/SSO)'),
                ],
                format_func=lambda x: x[1],
                key='new_rule_type'
            )[0]
            
            rebalance_freq = st.selectbox(
                '리밸런싱 주기',
                [
                    (RebalanceFrequency.MONTHLY, '월별'),
                    (RebalanceFrequency.QUARTERLY, '분기별'),
                    (RebalanceFrequency.SEMI_ANNUAL, '반년별'),
                    (RebalanceFrequency.ANNUAL, '연별'),
                    (RebalanceFrequency.NEVER, '없음 (Buy & Hold)'),
                ],
                format_func=lambda x: x[1],
                key='new_rebal_freq'
            )[0]
            
            description = st.text_area('규칙 설명', height=60)
            
            if st.form_submit_button('✅ 전략 만들기', type='primary'):
                if not strat_code or not account_name:
                    st.error('필수 항목을 입력하세요.')
                elif strat_code in [s.code for s in DataManager.get_strategies()]:
                    st.error('이미 존재하는 코드입니다.')
                else:
                    # 기본 규칙 생성
                    rules = RuleConfig(
                        rule_type=rule_type,
                        rebalance_frequency=rebalance_freq,
                        description=description,
                        version='1.0',
                        effective_date=date.today().isoformat()
                    )
                    
                    strategy = StrategyConfig(
                        code=strat_code,
                        account_name=account_name,
                        rules=rules
                    )
                    
                    DataManager.save_strategy(strategy)
                    st.success(f'✓ {strat_code} 전략을 만들었습니다.')
                    st.rerun()
    
    with tab2:
        st.subheader('기존 전략 수정')
        strategies = DataManager.get_strategies()
        
        if strategies:
            chosen = st.selectbox(
                '전략 선택',
                strategies,
                format_func=lambda s: f"{s.code} - {s.account_name}"
            )
            
            st.markdown(f"#### {chosen.code} 규칙 편집")
            
            with st.form(f'edit_strategy_{chosen.code}'):
                new_desc = st.text_area(
                    '규칙 설명',
                    value=chosen.rules.description,
                    height=60
                )
                
                if st.form_submit_button('✅ 규칙 업데이트', type='primary'):
                    # 기존 규칙을 버전 히스토리에 저장
                    chosen.rule_version_history.append({
                        'version': chosen.rules.version,
                        'effective_date': chosen.rules.effective_date,
                        'rules': chosen.rules.to_dict()
                    })
                    
                    # 새 버전 생성
                    version_parts = chosen.rules.version.split('.')
                    version_parts[-1] = str(int(version_parts[-1]) + 1)
                    new_version = '.'.join(version_parts)
                    
                    chosen.rules.version = new_version
                    chosen.rules.effective_date = date.today().isoformat()
                    chosen.rules.description = new_desc
                    chosen.last_modified = pd.Timestamp.now().isoformat()
                    
                    DataManager.save_strategy(chosen)
                    DataManager.save_strategy_version(chosen.code, chosen.rules)
                    
                    st.success(f'✓ {chosen.code} 규칙을 v{new_version}으로 업데이트했습니다.')
                    st.rerun()
        else:
            st.info('등록된 전략이 없습니다.')

elif page == '리밸런싱 히스토리':
    st.header('리밸런싱 히스토리')
    st.caption('모든 저장된 리밸런싱 실행 기록')
    
    snapshots = DataManager.get_snapshots(limit=50)
    
    if snapshots:
        for snap in snapshots:
            st.markdown(f"#### {snap['date']} · ₩{snap['total']:,.0f}")
            if snap['plan']:
                st.caption(snap['plan'])
    else:
        st.info('저장된 히스토리가 없습니다.')

elif page == '성과 분석':
    st.header('성과 분석')
    st.caption('CAGR · MDD · 벤치마크 비교')
    
    st.info('히스토리 데이터가 필요합니다.')

elif page == '설정':
    st.header('설정')
    st.caption('API 키, DB 경로, 기본 설정')
    
    st.markdown('#### 데이터베이스')
    st.code(str(DataManager.DB_PATH))
    
    if st.button('📥 백업 다운로드'):
        backup_data = {
            'strategies': [s.to_dict() for s in DataManager.get_strategies()],
            'snapshots': DataManager.get_snapshots(limit=None),
            'exported_at': pd.Timestamp.now().isoformat()
        }
        st.download_button(
            '💾 JSON 백업',
            json.dumps(backup_data, ensure_ascii=False, indent=2, default=str),
            file_name='portfolio_backup.json',
            mime='application/json'
        )
    
    if st.button('🗑 가격 캐시 삭제'):
        DataManager.clear_price_cache()
        st.success('캐시를 삭제했습니다.')
