# -*- coding: utf-8 -*-
"""리팩터 회귀 검증: 리팩터 전(하드코딩) 로직과 규칙 엔진 결과가 동일한지 비교한다.

app_orig.py 의 하드코딩 계획 블록을 그대로 복원한 run_old() 와,
strategy_engine.py 의 레지스트리 디스패치 run_new() 를 같은 입력으로 실행해
전략별(티커·목표금액·매매액·비고) 일치 여부를 출력한다.
"""
import json

import pandas as pd

import strategy_engine as se

# ---------- app 쪽 포맷 헬퍼와 동일 ----------
def n(v, default=0.0):
    try:
        if v is None or pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default

def p(x):
    return f'{x * 100:.2f}%'

# ---------- 리팩터 전 로직 (app_orig.py 의 하드코딩 블록을 그대로 재현) ----------
def run_old(cfgs, vdf, trigger_dd, run_date):
    QUARTER_END = run_date.month in (3, 6, 9, 12)
    plan_rows = []

    laa_all = vdf[vdf['전략'] == 'LAA'] if not vdf.empty else vdf
    if not laa_all.empty:
        laa = laa_all[laa_all['티커'] != 'CASH']; cash_row = laa_all[laa_all['티커'] == 'CASH']
        cash_cur = n(cash_row['현재금액'].sum()); total = laa['현재금액'].sum() + cash_cur
        cash_pct = n(cash_row['목표%'].sum())
        for _, r in laa.iterrows():
            filtered = r['티커'] in ('133690', '245350'); breached = filtered and r['SMA 위'] == 'NO'
            if breached: cash_pct += r['목표%']
            if QUARTER_END or breached:
                tgt = 0.0 if breached else total * r['목표%'] / 100
                note = 'SMA 이탈 → 현금화' if breached else ('목표비중 복원(분기말)' if QUARTER_END else '유지')
                plan_rows.append({'전략': 'LAA', '티커': r['티커'], 'ETF': r['ETF'], '현재금액': r['현재금액'], '목표금액': tgt, '매매액(+매수/-매도)': tgt - r['현재금액'], '비고': note})
            else:
                plan_rows.append({'전략': 'LAA', '티커': r['티커'], 'ETF': r['ETF'], '현재금액': r['현재금액'], '목표금액': r['현재금액'], '매매액(+매수/-매도)': 0.0, '비고': '유지(분기중)'})
        cash_tgt = total * cash_pct / 100
        plan_rows.append({'전략': 'LAA', '티커': 'CASH', 'ETF': '현금', '현재금액': cash_cur, '목표금액': cash_tgt, '매매액(+매수/-매도)': cash_tgt - cash_cur, '비고': '필터 이탈 자산 보관'})

    gsm_all = vdf[vdf['전략'] == 'GSM'] if not vdf.empty else vdf
    if not gsm_all.empty:
        gsm = gsm_all[gsm_all['티커'] != 'CASH']; cash_row = gsm_all[gsm_all['티커'] == 'CASH']
        cash_cur = n(cash_row['현재금액'].sum()); total = gsm['현재금액'].sum() + cash_cur
        passing = gsm[gsm['SMA 위'] == 'YES'].sort_values('12M', ascending=False)
        winner = passing.iloc[0] if not passing.empty else None
        for _, r in gsm.iterrows():
            is_winner = winner is not None and r['티커'] == winner['티커']
            tgt = total * 0.8 if is_winner else 0.0
            note = '선정(80%)' if is_winner else ('SMA 이탈' if r['SMA 위'] == 'NO' else ('데이터부족' if r['SMA 위'] == '데이터부족' else '미선정(순위 밀림)'))
            plan_rows.append({'전략': 'GSM', '티커': r['티커'], 'ETF': r['ETF'], '현재금액': r['현재금액'], '목표금액': tgt, '매매액(+매수/-매도)': tgt - r['현재금액'], '비고': note})
        cash_tgt = total * (0.2 if winner is not None else 1.0)
        plan_rows.append({'전략': 'GSM', '티커': 'CASH', 'ETF': '현금', '현재금액': cash_cur, '목표금액': cash_tgt, '매매액(+매수/-매도)': cash_tgt - cash_cur, '비고': '전략 대기현금' if winner is not None else '전 후보 SMA 이탈'})

    isa_all = vdf[vdf['전략'] == 'ISA'] if not vdf.empty else vdf
    if not isa_all.empty:
        isa = isa_all[isa_all['티커'] != 'CASH']; cash_row = isa_all[isa_all['티커'] == 'CASH']
        if not isa.empty:
            r = isa.iloc[0]; dd = trigger_dd.get('ISA'); triggered = dd is not None and dd <= -0.10
            cash = n(cash_row['현재금액'].sum()); buy = cash / 2 if triggered else 0.0
            note = f'트리거 발동(QQQ 고점대비 {p(dd)}) → 현금 절반 분할매수' if triggered else f'대기(QQQ 고점대비 {p(dd) if dd is not None else "데이터 없음"})'
            plan_rows.append({'전략': 'ISA', '티커': r['티커'], 'ETF': r['ETF'], '현재금액': r['현재금액'], '목표금액': r['현재금액'] + buy, '매매액(+매수/-매도)': buy, '비고': note})
            plan_rows.append({'전략': 'ISA', '티커': 'CASH', 'ETF': '현금', '현재금액': cash, '목표금액': cash - buy, '매매액(+매수/-매도)': -buy, '비고': '매수 재원'})

    sso = vdf[vdf['전략'] == 'SSO'] if not vdf.empty else vdf
    if not sso.empty:
        total = sso['현재금액'].sum(); dd = trigger_dd.get('SSO'); triggered = dd is not None and dd <= -0.15
        stock_pct = 85.0 if triggered else 70.0
        for _, r in sso.iterrows():
            is_stock = r['티커'] == '360750'; tgt = total * (stock_pct if is_stock else 100 - stock_pct) / 100
            note = (f'트리거 발동(고점대비 {p(dd)}) → 현금 절반 투입' if triggered else f'평시 유지(고점대비 {p(dd) if dd is not None else "데이터 없음"})') if is_stock else ('트리거 발동 → 현금 축소' if triggered else '평시 유지')
            plan_rows.append({'전략': 'SSO', '티커': r['티커'], 'ETF': r['ETF'], '현재금액': r['현재금액'], '목표금액': tgt, '매매액(+매수/-매도)': tgt - r['현재금액'], '비고': note})

    em = vdf[vdf['전략'] == 'EM'] if not vdf.empty else vdf
    if not em.empty:
        for _, r in em.iterrows():
            plan_rows.append({'전략': 'EM', '티커': r['티커'] or '-', 'ETF': r['ETF'], '현재금액': r['현재금액'], '목표금액': r['현재금액'], '매매액(+매수/-매도)': 0.0, '비고': '매매 없음(연 1회만 허용)'})

    for cfg in cfgs:
        code = cfg['code']
        if code in ('LAA', 'GSM', 'ISA', 'SSO', 'EM') or vdf.empty:
            continue
        sub_all = vdf[vdf['전략'] == code]
        if sub_all.empty: continue
        sub = sub_all[sub_all['티커'] != 'CASH']; cash_row = sub_all[sub_all['티커'] == 'CASH']
        cash = n(cash_row['현재금액'].sum()); total = sub['현재금액'].sum() + cash
        for _, r in sub.iterrows():
            tgt = total * n(r['목표%']) / 100
            plan_rows.append({'전략': code, '티커': r['티커'], 'ETF': r['ETF'], '현재금액': r['현재금액'], '목표금액': tgt, '매매액(+매수/-매도)': tgt - r['현재금액'], '비고': '목표비중 리밸런싱'})
        if not cash_row.empty:
            cash_tgt = total * n(cash_row['목표%'].sum()) / 100
            plan_rows.append({'전략': code, '티커': 'CASH', 'ETF': '현금', '현재금액': cash, '목표금액': cash_tgt, '매매액(+매수/-매도)': cash_tgt - cash, '비고': '현금 목표비중'})
    return plan_rows

# ---------- 리팩터 후 로직 (규칙 엔진 디스패치) ----------
def run_new(cfgs, vdf, trigger_dd, run_date):
    specs = se.specs_from_text(se.DEFAULT_SPECS)
    QUARTER_END = run_date.month in (3, 6, 9, 12)
    ctx = {'quarter_end': QUARTER_END, 'trigger_dd': trigger_dd}
    plan_rows = []
    for code in se.ordered_codes(cfgs, specs):
        if vdf.empty:
            break
        sub_all = vdf[vdf['전략'] == code]
        if sub_all.empty:
            continue
        spec = specs.get(code)
        if spec is not None:
            plan_rows.extend(se.apply_strategy(spec, vdf, ctx))
        else:
            sub = sub_all[sub_all['티커'] != 'CASH']; cash_row = sub_all[sub_all['티커'] == 'CASH']
            cash = n(cash_row['현재금액'].sum()); total = sub['현재금액'].sum() + cash
            for _, r in sub.iterrows():
                tgt = total * n(r['목표%']) / 100
                plan_rows.append({'전략': code, '티커': r['티커'], 'ETF': r['ETF'], '현재금액': r['현재금액'], '목표금액': tgt, '매매액(+매수/-매도)': tgt - r['현재금액'], '비고': '목표비중 리밸런싱'})
            if not cash_row.empty:
                cash_tgt = total * n(cash_row['목표%'].sum()) / 100
                plan_rows.append({'전략': code, '티커': 'CASH', 'ETF': '현금', '현재금액': cash, '목표금액': cash_tgt, '매매액(+매수/-매도)': cash_tgt - cash, '비고': '현금 목표비중'})
    return plan_rows

# ---------- 합성 데이터 ----------
ROW_DEFS = [
    # strategy, ticker, name, role, target_pct, value
    ('LAA', '133690', 'TIGER 미국나스닥100', 'NASDAQ', 12.5, 1000),
    ('LAA', '245350', 'TIGER 유로스탁스배당30', 'EuroStoxx', 12.5, 1000),
    ('LAA', '360750', 'TIGER 미국S&P500', 'S&P500', 12.5, 1000),
    ('LAA', '251350', 'KODEX 선진국MSCI World', 'MSCI World', 15.5, 1000),
    ('LAA', '132030', 'KODEX 골드선물(H)', 'Gold', 25.0, 1000),
    ('LAA', '148070', 'KIWOOM 국고채10년', 'Bond', 22.0, 1000),
    ('LAA', 'CASH', '현금', '필터이탈 대기현금', 0.0, 0),
    ('GSM', '360750', 'TIGER 미국S&P500', 'GSM 후보', 0.0, 800),
    ('GSM', '251350', 'KODEX 선진국MSCI World', 'GSM 후보', 0.0, 800),
    ('GSM', '133690', 'TIGER 미국나스닥100', 'GSM 후보', 0.0, 800),
    ('GSM', '245350', 'TIGER 유로스탁스배당30', 'GSM 후보', 0.0, 800),
    ('GSM', 'CASH', '현금', '대기현금', 20.0, 1600),
    ('ISA', '418660', 'TIGER 미국나스닥100레버리지(합성)', '-10% 트리거', 0.0, 1000),
    ('ISA', 'CASH', '현금', '대기현금', 100.0, 4000),
    ('SSO', '360750', 'TIGER 미국S&P500', 'S&P500 기준', 70.0, 7000),
    ('SSO', '153130', 'KODEX 단기채권', '현금성', 30.0, 3000),
    ('EM', '069500', 'KODEX 200', '한국', 25.0, 2500),
    ('EM', '', '중국 ETF 입력', '중국', 25.0, 2500),
    ('EM', '', '인도 ETF 입력', '인도', 25.0, 2500),
    ('EM', '', '베트남 ETF 입력', '베트남', 25.0, 2500),
]
MOM12 = {'360750': 0.12, '251350': 0.09, '133690': 0.15, '245350': -0.02}

def build_vdf(sma_flags, cash_overrides=None):
    rows = []
    for i, (strat, tk, nm, role, tgt, val) in enumerate(ROW_DEFS):
        close = 1.0 if tk == 'CASH' else 100.0
        flag = '—' if tk == 'CASH' else sma_flags.get(tk, 'YES')
        rows.append({'idx': i, '전략': strat, '티커': tk, 'ETF': nm, 'role': role, '종가': close,
                     'SMA10': 100.0 if tk != 'CASH' else None, 'SMA 위': flag,
                     '12M': MOM12.get(tk) if tk != 'CASH' else None,
                     '현재금액': float(val), '목표%': float(tgt)})
    return pd.DataFrame(rows)

def cmp_rows(old_rows, new_rows):
    """(전략,티커,목표금액,매매액,비고) 기준 비교."""
    def norm(rows):
        return [(r['전략'], r['티커'], round(float(r['목표금액']), 2), round(float(r['매매액(+매수/-매도)']), 2), r['비고']) for r in rows]
    return norm(old_rows) == norm(new_rows), norm(old_rows), norm(new_rows)

CFGS = [{'code': c} for c in ['LAA', 'GSM', 'ISA', 'SSO', 'EM']]

SCENARIOS = [
    ('S1: 전 종목 SMA 통과, 분기중, 트리거 대기', build_vdf({}), {}, __import__('datetime').date(2026, 2, 15)),
    ('S2: 나스닥 SMA 이탈, 분기중', build_vdf({'133690': 'NO'}), {}, __import__('datetime').date(2026, 2, 15)),
    ('S3: 분기말 목표비중 복원', build_vdf({}), {}, __import__('datetime').date(2026, 3, 31)),
    ('S4: ISA -12% / SSO -20% 트리거 발동', build_vdf({}), {'ISA': -0.12, 'SSO': -0.20}, __import__('datetime').date(2026, 2, 15)),
    ('S5: ISA -5% / SSO -5% 트리거 미발동', build_vdf({}), {'ISA': -0.05, 'SSO': -0.05}, __import__('datetime').date(2026, 2, 15)),
    ('S6: GSM 후보 전원 이탈', build_vdf({'360750': 'NO', '251350': 'NO', '133690': 'NO', '245350': 'NO'}), {}, __import__('datetime').date(2026, 2, 15)),
]

fails = 0
for name, vdf, tdd, rd in SCENARIOS:
    old = run_old(CFGS, vdf, tdd, rd)
    new = run_new(CFGS, vdf, tdd, rd)
    ok, o_n, n_n = cmp_rows(old, new)
    print(('PASS  ' if ok else 'FAIL  ') + name)
    if not ok:
        fails += 1
        print('  old:', json.dumps(o_n, ensure_ascii=False, default=str))
        print('  new:', json.dumps(n_n, ensure_ascii=False, default=str))

# 사용자 추가 전략(스펙 없음 → static) 도 비교
extra_cfgs = CFGS + [{'code': 'CORE2'}]
extra_vdf = build_vdf({})
extra_vdf = pd.concat([extra_vdf, pd.DataFrame([{'idx': 99, '전략': 'CORE2', '티커': '069500', 'ETF': 'KODEX 200', 'role': '사용자 추가', '종가': 100.0, 'SMA10': None, 'SMA 위': '—', '12M': None, '현재금액': 3000.0, '목표%': 60.0},
                                                 {'idx': 100, '전략': 'CORE2', '티커': 'CASH', 'ETF': '현금', 'role': '대기현금', '종가': 1.0, 'SMA10': None, 'SMA 위': '—', '12M': None, '현재금액': 2000.0, '목표%': 40.0}])], ignore_index=True)
old = run_old(extra_cfgs, extra_vdf, {}, __import__('datetime').date(2026, 2, 15))
new = run_new(extra_cfgs, extra_vdf, {}, __import__('datetime').date(2026, 2, 15))
ok, _, _ = cmp_rows(old, new)
print(('PASS  ' if ok else 'FAIL  ') + 'S7: 사용자 추가 전략(static) 포함 전체 순서')
if not ok:
    fails += 1

print()
print('REGRESSION_RESULT:', 'ALL_PASS' if fails == 0 else f'{fails} FAILURES')
