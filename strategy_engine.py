# -*- coding: utf-8 -*-
"""전략 스펙 + 규칙 엔진 (하드코딩 제거용)

- 전략 정의(자산 유니버스·목표비중·리밸런싱 규칙·파라미터)는 코드가 아니라
  strategy_spec.json (없으면 아래 DEFAULT_SPECS 템플릿으로 자동 생성)에 둔다.
- 리밸런싱 규칙은 RULE_REGISTRY에 등록된 함수로 디스패치된다 (if/elif 제거).
- 새 전략 = 스펙 파일에 rule만 지정하면 끝. 파라미터는 params로 조정한다.
- Streamlit에 의존하지 않는 순수 계산 모듈 (테스트 가능).
"""
import json
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# 기본 스펙 템플릿 — strategy_spec.json 이 없을 때 이 내용으로 파일을 자동 생성한다.
# 이후 전략 변경은 모두 이 파일(또는 설정 페이지)에서만 하면 되고 코드 수정은 없다.
# ---------------------------------------------------------------------------
DEFAULT_SPECS = json.dumps({
    "strategies": [
        {
            "code": "LAA", "account": "과세 연금저축", "display_order": 0,
            "description": "변형 LAA — 나스닥/유로스탁스만 10개월 SMA 필터, 이탈 시 현금화. 목표비중 복원은 분기 말에만.",
            "dynamic": False, "active": True, "annual_limit": 0.0,
            "rule": "sma_filter_rebalance",
            "params": {"sma_roles": ["NASDAQ", "EuroStoxx"], "sma_months": 10, "quarter_end_restore": True},
            "assets": [
                {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KR", "role": "NASDAQ", "target_pct": 12.5, "category": "선진국 주식"},
                {"ticker": "245350", "name": "TIGER 유로스탁스배당30", "market": "KR", "role": "EuroStoxx", "target_pct": 12.5, "category": "선진국 주식"},
                {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KR", "role": "S&P500", "target_pct": 12.5, "category": "선진국 주식"},
                {"ticker": "251350", "name": "KODEX 선진국MSCI World", "market": "KR", "role": "MSCI World", "target_pct": 15.5, "category": "선진국 주식"},
                {"ticker": "132030", "name": "KODEX 골드선물(H)", "market": "KR", "role": "Gold", "target_pct": 25.0, "category": "금"},
                {"ticker": "148070", "name": "KIWOOM 국고채10년", "market": "KR", "role": "Bond", "target_pct": 22.0, "category": "선진국 채권"},
                {"ticker": "CASH", "name": "현금", "market": "KR", "role": "필터이탈 대기현금", "target_pct": 0.0, "category": "현금"}
            ]
        },
        {
            "code": "GSM", "account": "비과세 연금저축", "display_order": 1,
            "description": "글로벌 단순 모멘텀 — SMA 통과 후보 중 12개월 수익률 1위에 80% 투자, 20% 현금. 월 1회 리밸런싱.",
            "dynamic": True, "active": True, "annual_limit": 0.0,
            "rule": "momentum_rotate",
            "params": {"sma_qualify": True, "winner_share": 0.8, "cash_winner_share": 0.2, "cash_no_winner": 1.0},
            "assets": [
                {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KR", "role": "GSM 후보", "target_pct": 0.0, "category": "선진국 주식"},
                {"ticker": "251350", "name": "KODEX 선진국MSCI World", "market": "KR", "role": "GSM 후보", "target_pct": 0.0, "category": "선진국 주식"},
                {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KR", "role": "GSM 후보", "target_pct": 0.0, "category": "선진국 주식"},
                {"ticker": "245350", "name": "TIGER 유로스탁스배당30", "market": "KR", "role": "GSM 후보", "target_pct": 0.0, "category": "선진국 주식"},
                {"ticker": "CASH", "name": "현금", "market": "KR", "role": "대기현금", "target_pct": 20.0, "category": "현금"}
            ]
        },
        {
            "code": "ISA", "account": "ISA", "display_order": 2,
            "description": "나스닥 레버리지 트리거 — 나스닥100 고점대비 -10% 하락 시 분할매수.",
            "dynamic": False, "active": True, "annual_limit": 0.0,
            "rule": "drawdown_buy",
            "params": {"signal": {"ticker": "QQQ", "market": "US", "lookback_days": 120}, "threshold": -0.10, "buy_fraction": 0.5},
            "assets": [
                {"ticker": "418660", "name": "TIGER 미국나스닥100레버리지(합성)", "market": "KR", "role": "-10% 트리거", "target_pct": 0.0, "category": "선진국 주식", "signal_ticker": "QQQ"},
                {"ticker": "CASH", "name": "현금", "market": "KR", "role": "대기현금", "target_pct": 100.0, "category": "현금"}
            ]
        },
        {
            "code": "SSO", "account": "일반계좌 2", "display_order": 3,
            "description": "S&P500 ETF + 현금성 자산. S&P500 고점대비 -15% 하락 시 현금 절반 투입.",
            "dynamic": False, "active": True, "annual_limit": 0.0,
            "rule": "drawdown_shift",
            "params": {"signal": {"ticker": "360750", "market": "KR", "lookback_days": 120},
                       "threshold": -0.15, "normal_stock_pct": 70.0, "triggered_stock_pct": 85.0, "stock_role": "S&P500 기준"},
            "assets": [
                {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KR", "role": "S&P500 기준", "target_pct": 70.0, "category": "선진국 주식"},
                {"ticker": "153130", "name": "KODEX 단기채권", "market": "KR", "role": "현금성", "target_pct": 30.0, "category": "현금"}
            ]
        },
        {
            "code": "EM", "account": "일반계좌 1", "display_order": 4,
            "description": "신흥국 분산 장기보유. 리밸런싱은 연 1회 정도만.",
            "dynamic": False, "active": True, "annual_limit": 0.0,
            "rule": "hold",
            "params": {"hold_note": "매매 없음(연 1회만 허용)"},
            "assets": [
                {"ticker": "069500", "name": "KODEX 200", "market": "KR", "role": "한국", "target_pct": 25.0, "category": "신흥국 주식"},
                {"ticker": "", "name": "중국 ETF 입력", "market": "KR", "role": "중국", "target_pct": 25.0, "category": "신흥국 주식"},
                {"ticker": "", "name": "인도 ETF 입력", "market": "KR", "role": "인도", "target_pct": 25.0, "category": "신흥국 주식"},
                {"ticker": "", "name": "베트남 ETF 입력", "market": "KR", "role": "베트남", "target_pct": 25.0, "category": "신흥국 주식"}
            ]
        }
    ]
}, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 스펙 로딩
# ---------------------------------------------------------------------------
def specs_from_text(txt):
    """JSON 문자열 -> {code: spec} 딕셔너리."""
    data = json.loads(txt)
    return {s['code']: s for s in data['strategies']}


def load_specs(path):
    """스펙 파일 경로 -> {code: spec} 딕셔너리."""
    with open(path, encoding='utf-8') as f:
        return specs_from_text(f.read())


def ensure_spec_file(path):
    """스펙 파일이 없으면 기본 템플릿으로 생성한다. (실패해도 앱 동작은 유지)"""
    try:
        p = Path(path)
        if not p.exists():
            p.write_text(DEFAULT_SPECS, encoding='utf-8')
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 공용 헬퍼 (원래 app 의 n()/p() 와 동일 포맷)
# ---------------------------------------------------------------------------
def _n(v, default=0.0):
    try:
        if v is None or pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def _pf(x):
    return f'{x * 100:.2f}%'


# ---------------------------------------------------------------------------
# 규칙 레지스트리 — 새 규칙은 @register_rule('이름') 으로 추가하면
# 스펙 파일에서 rule: '이름' 만 지정해 사용할 수 있다.
# ---------------------------------------------------------------------------
RULE_REGISTRY = {}

RULE_DESC = {
    'static': '정적 비중 복원 (사용자 추가 전략 기본)',
    'sma_filter_rebalance': 'SMA 필터 + 분기말 목표 복원 (LAA형)',
    'momentum_rotate': '모멘텀 로테이션 — SMA 통과 후보 중 12M 1위 (GSM형)',
    'drawdown_buy': '낙폭 트리거 분할매수 — 신호 고점대비 하락 시 현금 일부 투입 (ISA형)',
    'drawdown_shift': '낙폭 트리거 비중 전환 — 발동 시 주식 비중 상향 (SSO형)',
    'hold': '보유 유지 — 리밸런싱 없음 (EM형)',
}


# 설정 화면은 이 메타데이터를 읽어 자동으로 입력칸을 만든다.
# 전략별 숫자/종목/조건은 strategy_spec.json에 저장되고, 앱 화면 코드는 전략마다 따로 하드코딩하지 않는다.
RULE_LABELS = {
    'static': '목표비중으로 맞추기',
    'sma_filter_rebalance': '추세(SMA) 필터 + 정기 복원',
    'momentum_rotate': '모멘텀 1등 자산 선택',
    'drawdown_buy': '고점 대비 하락 시 분할매수',
    'drawdown_shift': '고점 대비 하락 시 비중 전환',
    'hold': '장기 보유(자동 리밸런싱 없음)',
}

# path: params 안의 위치. type에 따라 앱이 적절한 Streamlit 위젯을 자동 생성한다.
RULE_UI_SCHEMA = {
    'static': [],
    'sma_filter_rebalance': [
        {'path': ['sma_roles'], 'label': 'SMA를 적용할 역할', 'type': 'csv_list', 'default': [],
         'help': '쉼표로 구분합니다. 예: NASDAQ, EuroStoxx'},
        {'path': ['sma_months'], 'label': '이동평균 기간(개월)', 'type': 'int', 'default': 10, 'min': 1, 'max': 60, 'step': 1},
        {'path': ['quarter_end_restore'], 'label': '분기말에 목표비중으로 복원', 'type': 'bool', 'default': True},
    ],
    'momentum_rotate': [
        {'path': ['sma_qualify'], 'label': 'SMA 통과 자산만 후보로 사용', 'type': 'bool', 'default': True},
        {'path': ['winner_share'], 'label': '1등 자산 투자비중(%)', 'type': 'fraction_pct', 'default': 0.80, 'min': 0.0, 'max': 100.0, 'step': 1.0},
        {'path': ['cash_winner_share'], 'label': '1등 선정 시 현금비중(%)', 'type': 'fraction_pct', 'default': 0.20, 'min': 0.0, 'max': 100.0, 'step': 1.0},
        {'path': ['cash_no_winner'], 'label': '통과 자산이 없을 때 현금비중(%)', 'type': 'fraction_pct', 'default': 1.0, 'min': 0.0, 'max': 100.0, 'step': 1.0},
    ],
    'drawdown_buy': [
        {'path': ['signal', 'ticker'], 'label': '하락률 판단 기준 티커', 'type': 'text', 'default': 'QQQ'},
        {'path': ['signal', 'market'], 'label': '기준 티커 시장', 'type': 'select', 'options': ['US', 'KR'], 'default': 'US'},
        {'path': ['signal', 'lookback_days'], 'label': '최근 고점 확인 기간(거래일)', 'type': 'int', 'default': 120, 'min': 20, 'max': 500, 'step': 5},
        {'path': ['threshold'], 'label': '매수 발동 하락률(%)', 'type': 'fraction_pct', 'default': -0.10, 'min': -90.0, 'max': 0.0, 'step': 1.0,
         'help': '예: -10 입력 → 최근 고점 대비 -10% 이하에서 발동'},
        {'path': ['buy_fraction'], 'label': '발동 시 대기현금 투입비중(%)', 'type': 'fraction_pct', 'default': 0.50, 'min': 0.0, 'max': 100.0, 'step': 5.0},
    ],
    'drawdown_shift': [
        {'path': ['signal', 'ticker'], 'label': '하락률 판단 기준 티커', 'type': 'text', 'default': '360750'},
        {'path': ['signal', 'market'], 'label': '기준 티커 시장', 'type': 'select', 'options': ['KR', 'US'], 'default': 'KR'},
        {'path': ['signal', 'lookback_days'], 'label': '최근 고점 확인 기간(거래일)', 'type': 'int', 'default': 120, 'min': 20, 'max': 500, 'step': 5},
        {'path': ['threshold'], 'label': '비중 전환 발동 하락률(%)', 'type': 'fraction_pct', 'default': -0.15, 'min': -90.0, 'max': 0.0, 'step': 1.0},
        {'path': ['normal_stock_pct'], 'label': '평상시 주식비중(%)', 'type': 'float', 'default': 70.0, 'min': 0.0, 'max': 100.0, 'step': 1.0},
        {'path': ['triggered_stock_pct'], 'label': '발동 시 주식비중(%)', 'type': 'float', 'default': 85.0, 'min': 0.0, 'max': 100.0, 'step': 1.0},
        {'path': ['stock_role'], 'label': '주식 자산 역할명', 'type': 'text', 'default': 'S&P500 기준'},
    ],
    'hold': [
        {'path': ['hold_note'], 'label': '리밸런싱 메모', 'type': 'text', 'default': '매매 없음(연 1회만 허용)'},
    ],
}

def rule_friendly_name(rule):
    return RULE_LABELS.get(rule, rule)


def rule_ui_schema(rule):
    return RULE_UI_SCHEMA.get(rule, [])

# ---------------------------------------------------------------------------
# 스펙 파일 저장/관리 (설정 UI와 연동)
# ---------------------------------------------------------------------------
def save_specs(path, specs):
    """specs dict -> {strategies: [...]} JSON 파일로 저장."""
    data = {'strategies': [specs[c] for c in specs]}
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def upsert_spec_entry(path, code, rule='static', params=None, assets=None,
                      account=None, description='', dynamic=None, display_order=99):
    """전략 1건을 스펙에 추가/갱신한다 (없으면 새로 추가)."""
    ensure_spec_file(path)
    specs = load_specs(path)
    prev = specs.get(code, {})
    specs[code] = {
        'code': code,
        'account': account or prev.get('account', code),
        'display_order': prev.get('display_order', display_order),
        'description': description if description is not None else prev.get('description', ''),
        'dynamic': bool(dynamic) if dynamic is not None else prev.get('dynamic', False),
        'active': prev.get('active', True),
        'annual_limit': prev.get('annual_limit', 0.0),
        'rule': rule,
        'params': params if params is not None else prev.get('params', {}),
        'assets': assets if assets is not None else prev.get('assets', []),
    }
    save_specs(path, specs)


def remove_spec_entry(path, code):
    """스펙에서 전략 1건을 제거한다."""
    ensure_spec_file(path)
    specs = load_specs(path)
    if code in specs:
        del specs[code]
        save_specs(path, specs)


def specs_to_configs(specs):
    """스펙 dict -> 설정(KV 'strategies')용 계정/설명/동적/활성 항목 리스트.
    display_order 순서로 정렬해 기존 기본 전략 순서(LAA→GSM→ISA→SSO→EM)를 유지한다.
    """
    out = []
    for s in sorted(specs.values(), key=lambda x: x.get('display_order', 99)):
        out.append({'code': s['code'], 'account': s.get('account', s['code']),
                    'description': s.get('description', ''), 'dynamic': s.get('dynamic', False),
                    'active': s.get('active', True), 'annual_limit': s.get('annual_limit', 0.0)})
    return out


def register_rule(key):
    def deco(fn):
        RULE_REGISTRY[key] = fn
        return fn
    return deco


def apply_strategy(spec, vdf, ctx):
    """스펙 1건을 vdf(시그널 컬럼 포함 자산 표)에 적용해 plan 행 리스트를 반환한다."""
    rule = spec.get('rule', 'static')
    fn = RULE_REGISTRY.get(rule) or RULE_REGISTRY['static']
    return fn(spec, vdf, ctx)


def ordered_codes(cfgs, specs):
    """스펙의 display_order 순으로 정렬하고, 스펙에 없는(사용자 추가) 전략은 뒤에 DB 순서대로."""
    codes = [c['code'] for c in cfgs]
    known = [s['code'] for s in sorted(specs.values(), key=lambda x: x.get('display_order', 99))
             if s['code'] in codes]
    rest = [c for c in codes if c not in specs]
    return known + rest


def _split_cash(sub_all):
    sub = sub_all[sub_all['티커'] != 'CASH']
    cash_row = sub_all[sub_all['티커'] == 'CASH']
    cash_cur = _n(cash_row['현재금액'].sum())
    return sub, cash_row, cash_cur


# ---------------------------------------------------------------------------
# 규칙 1: 정적 비중 복원 (사용자 추가 전략 기본 규칙)
# ---------------------------------------------------------------------------
@register_rule('static')
def rule_static(spec, vdf, ctx):
    code = spec['code']
    sub_all = vdf[vdf['전략'] == code]
    if sub_all.empty:
        return []
    sub, cash_row, cash = _split_cash(sub_all)
    total = sub['현재금액'].sum() + cash
    rows = []
    for _, r in sub.iterrows():
        tgt = total * _n(r['목표%']) / 100
        rows.append({'전략': code, '티커': r['티커'], 'ETF': r['ETF'], '현재금액': r['현재금액'],
                     '목표금액': tgt, '매매액(+매수/-매도)': tgt - r['현재금액'], '비고': '목표비중 리밸런싱'})
    if not cash_row.empty:
        cash_tgt = total * _n(cash_row['목표%'].sum()) / 100
        rows.append({'전략': code, '티커': 'CASH', 'ETF': '현금', '현재금액': cash,
                     '목표금액': cash_tgt, '매매액(+매수/-매도)': cash_tgt - cash, '비고': '현금 목표비중'})
    return rows


# ---------------------------------------------------------------------------
# 규칙 2: SMA 필터 리밸런싱 (LAA형) — 지정 role 만 SMA 필터, 이탈분은 현금, 분기말 목표 복원
# ---------------------------------------------------------------------------
@register_rule('sma_filter_rebalance')
def rule_sma_filter_rebalance(spec, vdf, ctx):
    code = spec['code']
    params = spec.get('params') or {}
    sub_all = vdf[vdf['전략'] == code]
    if sub_all.empty:
        return []
    laa, cash_row, cash_cur = _split_cash(sub_all)
    total = laa['현재금액'].sum() + cash_cur
    cash_pct = _n(cash_row['목표%'].sum())
    sma_roles = params.get('sma_roles', [])
    quarter_end = bool(ctx.get('quarter_end', False))
    rows = []
    for _, r in laa.iterrows():
        filtered = r['role'] in sma_roles
        breached = filtered and r['SMA 위'] == 'NO'
        if breached:
            cash_pct += _n(r['목표%'])
        if quarter_end or breached:
            tgt = 0.0 if breached else total * _n(r['목표%']) / 100
            note = 'SMA 이탈 → 현금화' if breached else ('목표비중 복원(분기말)' if quarter_end else '유지')
            rows.append({'전략': code, '티커': r['티커'], 'ETF': r['ETF'], '현재금액': r['현재금액'],
                         '목표금액': tgt, '매매액(+매수/-매도)': tgt - r['현재금액'], '비고': note})
        else:
            rows.append({'전략': code, '티커': r['티커'], 'ETF': r['ETF'], '현재금액': r['현재금액'],
                         '목표금액': r['현재금액'], '매매액(+매수/-매도)': 0.0, '비고': '유지(분기중)'})
    cash_tgt = total * cash_pct / 100
    rows.append({'전략': code, '티커': 'CASH', 'ETF': '현금', '현재금액': cash_cur,
                 '목표금액': cash_tgt, '매매액(+매수/-매도)': cash_tgt - cash_cur, '비고': '필터 이탈 자산 보관'})
    return rows


# ---------------------------------------------------------------------------
# 규칙 3: 모멘텀 로테이션 (GSM형) — SMA 통과 후보 중 12M 1위에 winner_share, 나머지 현금
# ---------------------------------------------------------------------------
@register_rule('momentum_rotate')
def rule_momentum_rotate(spec, vdf, ctx):
    code = spec['code']
    params = spec.get('params') or {}
    sub_all = vdf[vdf['전략'] == code]
    if sub_all.empty:
        return []
    gsm, cash_row, cash_cur = _split_cash(sub_all)
    total = gsm['현재금액'].sum() + cash_cur
    passing = gsm[gsm['SMA 위'] == 'YES'].sort_values('12M', ascending=False)
    winner = passing.iloc[0] if not passing.empty else None
    win_share = float(params.get('winner_share', 0.8))
    rows = []
    for _, r in gsm.iterrows():
        is_winner = winner is not None and r['티커'] == winner['티커']
        tgt = total * win_share if is_winner else 0.0
        note = f'선정({int(win_share * 100)}%)' if is_winner else (
            'SMA 이탈' if r['SMA 위'] == 'NO' else ('데이터부족' if r['SMA 위'] == '데이터부족' else '미선정(순위 밀림)'))
        rows.append({'전략': code, '티커': r['티커'], 'ETF': r['ETF'], '현재금액': r['현재금액'],
                     '목표금액': tgt, '매매액(+매수/-매도)': tgt - r['현재금액'], '비고': note})
    cash_tgt = total * (float(params.get('cash_winner_share', 0.2)) if winner is not None else float(params.get('cash_no_winner', 1.0)))
    rows.append({'전략': code, '티커': 'CASH', 'ETF': '현금', '현재금액': cash_cur,
                 '목표금액': cash_tgt, '매매액(+매수/-매도)': cash_tgt - cash_cur,
                 '비고': '전략 대기현금' if winner is not None else '전 후보 SMA 이탈'})
    return rows


# ---------------------------------------------------------------------------
# 규칙 4: 낙폭 트리거 분할매수 (ISA형) — 신호 티커 고점대비 threshold 이하 시 현금 buy_fraction 매수
# ---------------------------------------------------------------------------
@register_rule('drawdown_buy')
def rule_drawdown_buy(spec, vdf, ctx):
    code = spec['code']
    params = spec.get('params') or {}
    sub_all = vdf[vdf['전략'] == code]
    if sub_all.empty:
        return []
    sub, cash_row, cash = _split_cash(sub_all)
    if sub.empty:
        return []
    r = sub.iloc[0]
    dd = (ctx.get('trigger_dd') or {}).get(code)
    threshold = float(params.get('threshold', -0.10))
    sig_name = (params.get('signal') or {}).get('ticker', '')
    triggered = dd is not None and dd <= threshold
    buy = cash * float(params.get('buy_fraction', 0.5)) if triggered else 0.0
    note = f'트리거 발동({sig_name} 고점대비 {_pf(dd)}) → 현금 절반 분할매수' if triggered else \
        f'대기({sig_name} 고점대비 {_pf(dd) if dd is not None else "데이터 없음"})'
    rows = [
        {'전략': code, '티커': r['티커'], 'ETF': r['ETF'], '현재금액': r['현재금액'],
         '목표금액': r['현재금액'] + buy, '매매액(+매수/-매도)': buy, '비고': note},
        {'전략': code, '티커': 'CASH', 'ETF': '현금', '현재금액': cash,
         '목표금액': cash - buy, '매매액(+매수/-매도)': -buy, '비고': '매수 재원'},
    ]
    return rows


# ---------------------------------------------------------------------------
# 규칙 5: 낙폭 트리거 비중 전환 (SSO형) — 발동 시 주식 비중을 triggered_stock_pct 로
# ---------------------------------------------------------------------------
@register_rule('drawdown_shift')
def rule_drawdown_shift(spec, vdf, ctx):
    code = spec['code']
    params = spec.get('params') or {}
    sub_all = vdf[vdf['전략'] == code]
    if sub_all.empty:
        return []
    total = sub_all['현재금액'].sum()
    dd = (ctx.get('trigger_dd') or {}).get(code)
    threshold = float(params.get('threshold', -0.15))
    triggered = dd is not None and dd <= threshold
    stock_pct = float(params.get('triggered_stock_pct', 85.0)) if triggered else float(params.get('normal_stock_pct', 70.0))
    stock_role = params.get('stock_role')
    rows = []
    for _, r in sub_all.iterrows():
        is_stock = r['role'] == stock_role
        tgt = total * (stock_pct if is_stock else 100 - stock_pct) / 100
        if is_stock:
            note = (f'트리거 발동(고점대비 {_pf(dd)}) → 현금 절반 투입' if triggered else
                    f'평시 유지(고점대비 {_pf(dd) if dd is not None else "데이터 없음"})')
        else:
            note = '트리거 발동 → 현금 축소' if triggered else '평시 유지'
        rows.append({'전략': code, '티커': r['티커'], 'ETF': r['ETF'], '현재금액': r['현재금액'],
                     '목표금액': tgt, '매매액(+매수/-매도)': tgt - r['현재금액'], '비고': note})
    return rows


# ---------------------------------------------------------------------------
# 규칙 6: 보유 유지 (EM형) — 리밸런싱 없음
# ---------------------------------------------------------------------------
@register_rule('hold')
def rule_hold(spec, vdf, ctx):
    code = spec['code']
    note = (spec.get('params') or {}).get('hold_note', '매매 없음')
    sub_all = vdf[vdf['전략'] == code]
    if sub_all.empty:
        return []
    rows = []
    for _, r in sub_all.iterrows():
        rows.append({'전략': code, '티커': r['티커'] or '-', 'ETF': r['ETF'], '현재금액': r['현재금액'],
                     '목표금액': r['현재금액'], '매매액(+매수/-매도)': 0.0, '비고': note})
    return rows
