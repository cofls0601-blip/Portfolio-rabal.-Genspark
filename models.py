# models.py
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from enum import Enum
from datetime import datetime
import json

class RebalanceFrequency(str, Enum):
    """리밸런싱 주기"""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "semi_annual"
    ANNUAL = "annual"
    NEVER = "never"

class RuleType(str, Enum):
    """규칙 타입"""
    STATIC_WITH_FILTERS = "static_with_filters"
    DYNAMIC_MOMENTUM = "dynamic_momentum"
    BUY_AND_HOLD = "buy_and_hold"
    CUSTOM_TRIGGER = "custom_trigger"

class FilterType(str, Enum):
    """필터 타입"""
    SMA = "sma"
    MOMENTUM = "momentum"
    DRAWDOWN = "drawdown"
    VALUE_LEVEL = "value_level"

class FilterTrigger(str, Enum):
    """필터 트리거 조건"""
    ABOVE = "above"
    BELOW = "below"
    CROSS_ABOVE = "cross_above"
    CROSS_BELOW = "cross_below"

@dataclass
class FilterConfig:
    """필터 설정"""
    name: str
    filter_type: FilterType
    apply_to_tickers: List[str]  # 이 필터를 적용할 티커들
    trigger: FilterTrigger
    action: str  # "convert_to_cash", "exclude", "reduce_weight" 등
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    enabled: bool = True
    
    def to_dict(self):
        return {
            'name': self.name,
            'filter_type': self.filter_type.value,
            'apply_to_tickers': self.apply_to_tickers,
            'trigger': self.trigger.value,
            'action': self.action,
            'parameters': self.parameters,
            'description': self.description,
            'enabled': self.enabled
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data['name'],
            filter_type=FilterType(data['filter_type']),
            apply_to_tickers=data['apply_to_tickers'],
            trigger=FilterTrigger(data['trigger']),
            action=data['action'],
            parameters=data.get('parameters', {}),
            description=data.get('description', ''),
            enabled=data.get('enabled', True)
        )

@dataclass
class BaseAsset:
    """기본 자산 설정"""
    ticker: str
    name: str
    target_pct: float
    market: str = "KR"  # KR, US
    category: str = "기타"
    signal_ticker: Optional[str] = None  # 신호 판단용 다른 티커
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data):
        return cls(**data)

@dataclass
class RuleConfig:
    """규칙 설정 - 전략의 핵심"""
    rule_type: RuleType
    rebalance_frequency: RebalanceFrequency
    rebalance_dates: Optional[List[int]] = None  # 월(1-12) 또는 요일(0-6)
    
    # static_with_filters용
    base_assets: List[BaseAsset] = field(default_factory=list)
    filters: List[FilterConfig] = field(default_factory=list)
    
    # dynamic_momentum용
    momentum_lookback: int = 12  # 개월
    sma_period: int = 10  # 개월
    momentum_selection_count: int = 1  # 상위 N개 선택
    allocation_dict: Dict[str, float] = field(default_factory=dict)  # {winner: 0.8, cash: 0.2} 등
    
    # buy_and_hold용
    rebalance_note: str = "매매 없음"
    
    description: str = ""
    version: str = "1.0"
    effective_date: Optional[str] = None
    
    def to_dict(self):
        return {
            'rule_type': self.rule_type.value,
            'rebalance_frequency': self.rebalance_frequency.value,
            'rebalance_dates': self.rebalance_dates,
            'base_assets': [a.to_dict() for a in self.base_assets],
            'filters': [f.to_dict() for f in self.filters],
            'momentum_lookback': self.momentum_lookback,
            'sma_period': self.sma_period,
            'momentum_selection_count': self.momentum_selection_count,
            'allocation_dict': self.allocation_dict,
            'rebalance_note': self.rebalance_note,
            'description': self.description,
            'version': self.version,
            'effective_date': self.effective_date,
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            rule_type=RuleType(data['rule_type']),
            rebalance_frequency=RebalanceFrequency(data['rebalance_frequency']),
            rebalance_dates=data.get('rebalance_dates'),
            base_assets=[BaseAsset.from_dict(a) for a in data.get('base_assets', [])],
            filters=[FilterConfig.from_dict(f) for f in data.get('filters', [])],
            momentum_lookback=data.get('momentum_lookback', 12),
            sma_period=data.get('sma_period', 10),
            momentum_selection_count=data.get('momentum_selection_count', 1),
            allocation_dict=data.get('allocation_dict', {}),
            rebalance_note=data.get('rebalance_note', ''),
            description=data.get('description', ''),
            version=data.get('version', '1.0'),
            effective_date=data.get('effective_date'),
        )

@dataclass
class StrategyConfig:
    """전략 설정"""
    code: str
    account_name: str
    rules: RuleConfig
    active: bool = True
    notes: str = ""
    rule_version_history: List[Dict[str, Any]] = field(default_factory=list)
    created_date: str = field(default_factory=lambda: datetime.now().isoformat())
    last_modified: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self):
        return {
            'code': self.code,
            'account_name': self.account_name,
            'rules': self.rules.to_dict(),
            'active': self.active,
            'notes': self.notes,
            'rule_version_history': self.rule_version_history,
            'created_date': self.created_date,
            'last_modified': self.last_modified,
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            code=data['code'],
            account_name=data['account_name'],
            rules=RuleConfig.from_dict(data['rules']),
            active=data.get('active', True),
            notes=data.get('notes', ''),
            rule_version_history=data.get('rule_version_history', []),
            created_date=data.get('created_date', datetime.now().isoformat()),
            last_modified=data.get('last_modified', datetime.now().isoformat()),
        )

@dataclass
class AssetSnapshot:
    """자산 스냅샷 (포트폴리오 내 종목 한 줄)"""
    ticker: str
    name: str
    strategy_code: str
    market: str
    category: str
    shares: float
    close: float
    prices: List[float] = field(default_factory=list)
    role: str = ""
    target_pct: float = 0.0
    
    def current_value(self, fx_rate: Optional[float] = None) -> float:
        """현재 평가액 계산"""
        if self.ticker == "CASH":
            return self.shares
        value = self.shares * self.close
        if self.market == "US" and fx_rate:
            value *= fx_rate
        return value

@dataclass
class ActionItem:
    """리밸런싱 액션 아이템"""
    ticker: str
    name: str
    strategy_code: str
    current_value: float
    target_value: float
    action_amount: float  # 양수=매수, 음수=매도
    reason: str
    priority: int = 0  # 우선순위 (낮을수록 높음)
    
    def action_type(self) -> str:
        if abs(self.action_amount) < 1000:
            return "NO_ACTION"
        elif self.action_amount > 0:
            return "BUY"
        else:
            return "SELL"

@dataclass
class RebalanceResult:
    """리밸런싱 결과"""
    run_date: str
    actions: List[ActionItem]
    total_current_value: float
    total_target_value: float
    strategy_breakdowns: Dict[str, Dict[str, float]]  # {code: {current, target}}
    notes: str = ""
