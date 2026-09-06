# rules_engine.py
import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
from models import (
    RuleConfig, RuleType, FilterConfig, FilterType, FilterTrigger,
    BaseAsset, ActionItem, RebalanceResult, AssetSnapshot, StrategyConfig
)

class RuleEngine:
    """전략 규칙을 해석하고 실행하는 엔진"""
    
    def __init__(self, strategy: StrategyConfig, assets: List[AssetSnapshot], 
                 vdf: pd.DataFrame, trigger_dd: Dict[str, Optional[float]],
                 fx_rate: Optional[float] = None):
        """
        Args:
            strategy: 전략 설정
            assets: 현재 보유 자산 목록
            vdf: 종가·SMA·모멘텀 계산된 데이터프레임
            trigger_dd: 트리거용 드로다운 {strategy_code: dd_value}
            fx_rate: USD/KRW 환율
        """
        self.strategy = strategy
        self.assets = assets
        self.vdf = vdf
        self.trigger_dd = trigger_dd
        self.fx_rate = fx_rate
    
    def evaluate(self, run_date: date) -> RebalanceResult:
        """규칙을 평가하고 액션 리스트를 반환"""
        rule_type = self.strategy.rules.rule_type
        
        if rule_type == RuleType.STATIC_WITH_FILTERS:
            actions = self._eval_static_with_filters(run_date)
        elif rule_type == RuleType.DYNAMIC_MOMENTUM:
            actions = self._eval_dynamic_momentum(run_date)
        elif rule_type == RuleType.BUY_AND_HOLD:
            actions = self._eval_buy_and_hold()
        elif rule_type == RuleType.CUSTOM_TRIGGER:
            actions = self._eval_custom_trigger(run_date)
        else:
            actions = []
        
        # 액션 우선순위 정렬
        actions.sort(key=lambda x: (x.priority, -abs(x.action_amount)))
        
        # 통계
        strategy_vdf = self.vdf[self.vdf['전략'] == self.strategy.code]
        total_current = strategy_vdf['현재금액'].sum() if not strategy_vdf.empty else 0.0
        total_target = sum(a.target_value for a in actions)
        
        return RebalanceResult(
            run_date=run_date.isoformat(),
            actions=actions,
            total_current_value=total_current,
            total_target_value=total_target,
            strategy_breakdowns={},
            notes=f"적용 규칙 v{self.strategy.rules.version}"
        )
    
    def _should_rebalance(self, run_date: date) -> bool:
        """이 날짜에 리밸런싱해야 하는지 판정"""
        freq = self.strategy.rules.rebalance_frequency
        
        if freq == RebalanceFrequency.NEVER:
            return False
        elif freq == RebalanceFrequency.MONTHLY:
            return True
        elif freq == RebalanceFrequency.QUARTERLY:
            return run_date.month in (self.strategy.rules.rebalance_dates or [3, 6, 9, 12])
        elif freq == RebalanceFrequency.SEMI_ANNUAL:
            return run_date.month in (self.strategy.rules.rebalance_dates or [6, 12])
        elif freq == RebalanceFrequency.ANNUAL:
            return run_date.month in (self.strategy.rules.rebalance_dates or [12])
        
        return False
    
    def _eval_filter(self, filt: FilterConfig, asset_row: pd.Series) -> Tuple[bool, str]:
        """
        필터 조건을 평가
        반환: (필터 작동 여부, 상세 이유)
        """
        if not filt.enabled:
            return False, "필터 비활성화"
        
        if filt.filter_type == FilterType.SMA:
            return self._eval_sma_filter(filt, asset_row)
        elif filt.filter_type == FilterType.MOMENTUM:
            return self._eval_momentum_filter(filt, asset_row)
        elif filt.filter_type == FilterType.DRAWDOWN:
            return self._eval_drawdown_filter(filt, asset_row)
        elif filt.filter_type == FilterType.VALUE_LEVEL:
            return self._eval_value_filter(filt, asset_row)
        
        return False, "알 수 없는 필터"
    
    def _eval_sma_filter(self, filt: FilterConfig, asset_row: pd.Series) -> Tuple[bool, str]:
        """SMA 기반 필터"""
        sma = asset_row.get('SMA10')
        close = asset_row.get('종가')
        
        if sma is None or close is None:
            return False, "데이터 부족"
        
        if filt.trigger == FilterTrigger.ABOVE:
            triggered = close > sma
            reason = f"종가({close:.0f}) > SMA10({sma:.0f})" if triggered else f"종가({close:.0f}) <= SMA10({sma:.0f})"
        elif filt.trigger == FilterTrigger.BELOW:
            triggered = close < sma
            reason = f"종가({close:.0f}) < SMA10({sma:.0f})" if triggered else f"종가({close:.0f}) >= SMA10({sma:.0f})"
        else:
            triggered = False
            reason = "미지원 트리거"
        
        return triggered, reason
    
    def _eval_momentum_filter(self, filt: FilterConfig, asset_row: pd.Series) -> Tuple[bool, str]:
        """모멘텀 기반 필터"""
        mom = asset_row.get('12M')
        threshold = filt.parameters.get('threshold', 0.0)
        
        if mom is None:
            return False, "모멘텀 데이터 없음"
        
        if filt.trigger == FilterTrigger.ABOVE:
            triggered = mom > threshold
            reason = f"모멘텀({mom:.2%}) > 임계값({threshold:.2%})"
        elif filt.trigger == FilterTrigger.BELOW:
            triggered = mom < threshold
            reason = f"모멘텀({mom:.2%}) < 임계값({threshold:.2%})"
        else:
            triggered = False
            reason = ""
        
        return triggered, reason
    
    def _eval_drawdown_filter(self, filt: FilterConfig, asset_row: pd.Series) -> Tuple[bool, str]:
        """드로다운 트리거 필터 (ISA, SSO용)"""
        dd = asset_row.get('dd')
        threshold = filt.parameters.get('threshold', -0.10)
        
        if dd is None:
            return False, "드로다운 데이터 없음"
        
        triggered = dd <= threshold
        reason = f"드로다운({dd:.2%}) <= {threshold:.2%}" if triggered else f"드로다운({dd:.2%}) > {threshold:.2%}"
        
        return triggered, reason
    
    def _eval_value_filter(self, filt: FilterConfig, asset_row: pd.Series) -> Tuple[bool, str]:
        """값 기반 필터 (예: 가격이 특정값 이상)"""
        value = asset_row.get('종가')
        threshold = filt.parameters.get('threshold', 0.0)
        
        if value is None:
            return False, "가격 데이터 없음"
        
        if filt.trigger == FilterTrigger.ABOVE:
            triggered = value > threshold
        elif filt.trigger == FilterTrigger.BELOW:
            triggered = value < threshold
        else:
            triggered = False
        
        reason = f"가격({value:.0f}) {'>' if triggered else '<'} {threshold:.0f}"
        return triggered, reason
    
    def _eval_static_with_filters(self, run_date: date) -> List[ActionItem]:
        """LAA 같은 정적 + 필터 타입"""
        actions = []
        strategy_vdf = self.vdf[self.vdf['전략'] == self.strategy.code]
        
        if strategy_vdf.empty:
            return actions
        
        total = strategy_vdf['현재금액'].sum()
        should_rebal = self._should_rebalance(run_date)
        cash_needed_pct = 0.0
        
        # 기본 자산들 평가
        for base_asset in self.strategy.rules.base_assets:
            ticker = base_asset.ticker
            target_pct = base_asset.target_pct
            
            # 이 자산의 현재 행 찾기
            asset_rows = strategy_vdf[strategy_vdf['티커'] == ticker]
            if asset_rows.empty and ticker != 'CASH':
                continue
            
            if ticker == 'CASH':
                # 현금은 나중에 처리
                continue
            
            asset_row = asset_rows.iloc[0]
            cur_val = asset_row['현재금액']
            
            # 이 자산에 적용되는 필터들 확인
            applicable_filters = [
                f for f in self.strategy.rules.filters
                if ticker in f.apply_to_tickers
            ]
            
            is_filtered_out = False
            filter_reason = ""
            
            for filt in applicable_filters:
                triggered, reason = self._eval_filter(filt, asset_row)
                if triggered:
                    is_filtered_out = True
                    filter_reason = reason
                    if filt.action == "convert_to_cash":
                        cash_needed_pct += target_pct
                    break
            
            # 목표 계산
            if is_filtered_out:
                tgt = 0.0
                note = f"{filt.description} ({filter_reason})" if filt.description else f"필터 작동: {filter_reason}"
            elif should_rebal:
                tgt = total * target_pct / 100
                note = '목표비중 복원(리밸런싱 기준일)'
            else:
                tgt = cur_val
                note = '유지(리밸런싱 비대상)'
            
            actions.append(ActionItem(
                ticker=ticker,
                name=base_asset.name,
                strategy_code=self.strategy.code,
                current_value=cur_val,
                target_value=tgt,
                action_amount=tgt - cur_val,
                reason=note,
                priority=1 if is_filtered_out else 2
            ))
        
        # 현금 행 처리
        cash_rows = strategy_vdf[strategy_vdf['티커'] == 'CASH']
        cash_cur = cash_rows['현재금액'].sum() if not cash_rows.empty else 0.0
        cash_tgt = total * cash_needed_pct / 100 if total > 0 else 0.0
        
        actions.append(ActionItem(
            ticker='CASH',
            name='현금',
            strategy_code=self.strategy.code,
            current_value=cash_cur,
            target_value=cash_tgt,
            action_amount=cash_tgt - cash_cur,
            reason='필터 이탈 자산 대기현금',
            priority=3
        ))
        
        return actions
    
    def _eval_dynamic_momentum(self, run_date: date) -> List[ActionItem]:
        """GSM 같은 동적 모멘텀 타입"""
        actions = []
        strategy_vdf = self.vdf[self.vdf['전략'] == self.strategy.code]
        
        if strategy_vdf.empty:
            return actions
        
        # 현금 제외 자산들만 봄
        candidates = strategy_vdf[strategy_vdf['티커'] != 'CASH'].copy()
        
        if candidates.empty:
            return actions
        
        total = strategy_vdf['현재금액'].sum()
        
        # SMA 필터 적용
        sma_period = self.strategy.rules.sma_period
        sma_col = f'SMA{sma_period}'
        
        passing = candidates[candidates['티커'].apply(
            lambda t: candidates[candidates['티커'] == t].iloc[0].get(sma_col) is None or
                      candidates[candidates['티커'] == t].iloc[0]['종가'] >
                      candidates[candidates['티커'] == t].iloc[0].get(sma_col, 0)
        )]
        
        if passing.empty:
            # 모든 후보가 SMA 이탈 → 100% 현금
            for _, row in candidates.iterrows():
                actions.append(ActionItem(
                    ticker=row['티커'],
                    name=row['ETF'],
                    strategy_code=self.strategy.code,
                    current_value=row['현재금액'],
                    target_value=0.0,
                    action_amount=-row['현재금액'],
                    reason='모든 후보 SMA 이탈 → 현금화',
                    priority=1
                ))
            
            cash_rows = strategy_vdf[strategy_vdf['티커'] == 'CASH']
            cash_cur = cash_rows['현재금액'].sum() if not cash_rows.empty else 0.0
            
            actions.append(ActionItem(
                ticker='CASH',
                name='현금',
                strategy_code=self.strategy.code,
                current_value=cash_cur,
                target_value=total,
                action_amount=total - cash_cur,
                reason='모멘텀 대기현금 (전 후보 이탈)',
                priority=2
            ))
        else:
            # 통과 후보 중 모멘텀 상위 1개 선택
            passing_sorted = passing.sort_values('12M', ascending=False, na_position='last')
            winner = passing_sorted.iloc[0] if not passing_sorted.empty else None
            
            alloc = self.strategy.rules.allocation_dict or {'winner': 0.8, 'cash': 0.2}
            winner_pct = alloc.get('winner', 0.8)
            cash_pct = alloc.get('cash', 0.2)
            
            # 모든 후보에 대해 액션 생성
            for _, row in candidates.iterrows():
                is_winner = winner is not None and row['티커'] == winner['티커']
                tgt = total * winner_pct / 100 if is_winner else 0.0
                
                if is_winner:
                    note = f"모멘텀 1위 선정({row['12M']:.2%}) → {winner_pct*100:.0f}% 투자"
                elif row['SMA10'] is None or row['종가'] < row.get('SMA10', 0):
                    note = 'SMA 이탈'
                else:
                    note = '모멘텀 순위 밀림'
                
                actions.append(ActionItem(
                    ticker=row['티커'],
                    name=row['ETF'],
                    strategy_code=self.strategy.code,
                    current_value=row['현재금액'],
                    target_value=tgt,
                    action_amount=tgt - row['현재금액'],
                    reason=note,
                    priority=1 if is_winner else 2
                ))
            
            # 현금
            cash_rows = strategy_vdf[strategy_vdf['티커'] == 'CASH']
            cash_cur = cash_rows['현재금액'].sum() if not cash_rows.empty else 0.0
            cash_tgt = total * cash_pct / 100
            
            actions.append(ActionItem(
                ticker='CASH',
                name='현금',
                strategy_code=self.strategy.code,
                current_value=cash_cur,
                target_value=cash_tgt,
                action_amount=cash_tgt - cash_cur,
                reason=f'모멘텀 대기현금({cash_pct*100:.0f}%)',
                priority=3
            ))
        
        return actions
    
    def _eval_buy_and_hold(self) -> List[ActionItem]:
        """Buy & Hold - 매매 없음"""
        actions = []
        strategy_vdf = self.vdf[self.vdf['전략'] == self.strategy.code]
        
        for _, row in strategy_vdf.iterrows():
            actions.append(ActionItem(
                ticker=row['티커'],
                name=row['ETF'],
                strategy_code=self.strategy.code,
                current_value=row['현재금액'],
                target_value=row['현재금액'],
                action_amount=0.0,
                reason='Buy & Hold - 매매 없음',
                priority=5
            ))
        
        return actions
    
    def _eval_custom_trigger(self, run_date: date) -> List[ActionItem]:
        """ISA, SSO 같은 커스텀 트리거"""
        actions = []
        strategy_vdf = self.vdf[self.vdf['전략'] == self.strategy.code]
        
        if strategy_vdf.empty:
            return actions
        
        # 전략별 커스텀 로직
        if self.strategy.code == 'ISA':
            actions = self._eval_isa_trigger(strategy_vdf)
        elif self.strategy.code == 'SSO':
            actions = self._eval_sso_trigger(strategy_vdf)
        
        return actions
    
    def _eval_isa_trigger(self, strategy_vdf: pd.DataFrame) -> List[ActionItem]:
        """ISA: 나스닥100 고점대비 -10% 트리거"""
        actions = []
        
        isa_stock = strategy_vdf[strategy_vdf['티커'] != 'CASH']
        cash_row = strategy_vdf[strategy_vdf['티커'] == 'CASH']
        
        if isa_stock.empty or cash_row.empty:
            return actions
        
        dd = self.trigger_dd.get('ISA')
        triggered = dd is not None and dd <= -0.10
        
        stock = isa_stock.iloc[0]
        cash = cash_row.iloc[0]
        
        if triggered:
            buy_amt = cash['현재금액'] / 2
            actions.append(ActionItem(
                ticker=stock['티커'],
                name=stock['ETF'],
                strategy_code=self.strategy.code,
                current_value=stock['현재금액'],
                target_value=stock['현재금액'] + buy_amt,
                action_amount=buy_amt,
                reason=f"트리거 발동(신호 고점대비 {dd:.2%}) → 현금 절반 분할매수",
                priority=0
            ))
            
            actions.append(ActionItem(
                ticker='CASH',
                name='현금',
                strategy_code=self.strategy.code,
                current_value=cash['현재금액'],
                target_value=cash['현재금액'] - buy_amt,
                action_amount=-buy_amt,
                reason='매수 재원',
                priority=1
            ))
        else:
            dd_str = f"{dd:.2%}" if dd is not None else "데이터 없음"
            actions.append(ActionItem(
                ticker=stock['티커'],
                name=stock['ETF'],
                strategy_code=self.strategy.code,
                current_value=stock['현재금액'],
                target_value=stock['현재금액'],
                action_amount=0.0,
                reason=f"대기 상태(신호 고점대비 {dd_str})",
                priority=2
            ))
            
            actions.append(ActionItem(
                ticker='CASH',
                name='현금',
                strategy_code=self.strategy.code,
                current_value=cash['현재금액'],
                target_value=cash['현재금액'],
                action_amount=0.0,
                reason='대기현금',
                priority=3
            ))
        
        return actions
    
    def _eval_sso_trigger(self, strategy_vdf: pd.DataFrame) -> List[ActionItem]:
        """SSO: S&P500 고점대비 -15% 트리거"""
        actions = []
        
        stock = strategy_vdf[strategy_vdf['티커'] != 'CASH']
        cash = strategy_vdf[strategy_vdf['티커'] == 'CASH']
        
        if stock.empty or cash.empty:
            return actions
        
        total = strategy_vdf['현재금액'].sum()
        dd = self.trigger_dd.get('SSO')
        triggered = dd is not None and dd <= -0.15
        
        stock_pct = 85.0 if triggered else 70.0
        
        for _, row in stock.iterrows():
            tgt = total * stock_pct / 100
            dd_str = f"{dd:.2%}" if dd is not None else "데이터 없음"
            note = f"트리거({dd_str}) → {stock_pct:.0f}% 투자" if triggered else f"평시 유지({dd_str})"
            
            actions.append(ActionItem(
                ticker=row['티커'],
                name=row['ETF'],
                strategy_code=self.strategy.code,
                current_value=row['현재금액'],
                target_value=tgt,
                action_amount=tgt - row['현재금액'],
                reason=note,
                priority=1
            ))
        
        cash_row = cash.iloc[0]
        cash_tgt = total * (100 - stock_pct) / 100
        
        actions.append(ActionItem(
            ticker='CASH',
            name='현금',
            strategy_code=self.strategy.code,
            current_value=cash_row['현재금액'],
            target_value=cash_tgt,
            action_amount=cash_tgt - cash_row['현재금액'],
            reason='현금 비중 조정',
            priority=2
        ))
        
        return actions
