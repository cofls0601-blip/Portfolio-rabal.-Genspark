# data_manager.py
import sqlite3
import json
import pandas as pd
from pathlib import Path
from datetime import date, datetime
from typing import List, Dict, Optional, Any
from models import StrategyConfig, RuleConfig, FilterConfig, BaseAsset

DB_DIR = Path.home() / '.asset_allocation_app'
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / 'portfolio.db'

class DataManager:
    """SQLite 기반 데이터 관리"""
    
    @staticmethod
    def init_db():
        """DB 초기화"""
        con = sqlite3.connect(DB_PATH)
        con.execute('''
            CREATE TABLE IF NOT EXISTS kv (
                k TEXT PRIMARY KEY,
                v TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        con.execute('''
            CREATE TABLE IF NOT EXISTS price_cache (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                close REAL NOT NULL,
                PRIMARY KEY(ticker, date)
            )
        ''')
        con.execute('''
            CREATE TABLE IF NOT EXISTS strategy_version_history (
                strategy_code TEXT NOT NULL,
                version TEXT NOT NULL,
                effective_date TEXT NOT NULL,
                rules_json TEXT NOT NULL,
                PRIMARY KEY(strategy_code, version)
            )
        ''')
        con.execute('''
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                total_value REAL NOT NULL,
                composition_json TEXT,
                plan_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        con.commit()
        con.close()
    
    @staticmethod
    def get_state(key: str, default=None) -> Any:
        """상태 조회"""
        DataManager.init_db()
        con = sqlite3.connect(DB_PATH)
        try:
            row = con.execute('SELECT v FROM kv WHERE k=?', (key,)).fetchone()
            con.close()
            
            if row:
                return json.loads(row[0])
            return default if default is not None else {}
        except Exception:
            con.close()
            return default if default is not None else {}
    
    @staticmethod
    def put_state(key: str, value: Any):
        """상태 저장"""
        DataManager.init_db()
        con = sqlite3.connect(DB_PATH)
        con.execute(
            'INSERT OR REPLACE INTO kv(k, v) VALUES(?, ?)',
            (key, json.dumps(value, ensure_ascii=False, default=str))
        )
        con.commit()
        con.close()
    
    @staticmethod
    def get_strategies() -> List[StrategyConfig]:
        """모든 전략 조회"""
        data = DataManager.get_state('strategies', [])
        return [StrategyConfig.from_dict(d) for d in data]
    
    @staticmethod
    def save_strategy(strategy: StrategyConfig):
        """전략 저장"""
        strategies = DataManager.get_strategies()
        strategies = [s for s in strategies if s.code != strategy.code]
        strategies.append(strategy)
        DataManager.put_state('strategies', [s.to_dict() for s in strategies])
    
    @staticmethod
    def delete_strategy(code: str):
        """전략 삭제"""
        strategies = DataManager.get_strategies()
        strategies = [s for s in strategies if s.code != code]
        DataManager.put_state('strategies', [s.to_dict() for s in strategies])
    
    @staticmethod
    def save_price_cache(ticker: str, rows: List[Dict]):
        """가격 캐시 저장"""
        if not rows:
            return
        
        DataManager.init_db()
        con = sqlite3.connect(DB_PATH)
        con.executemany(
            'INSERT OR REPLACE INTO price_cache(ticker, date, close) VALUES(?, ?, ?)',
            [(ticker, r['date'], r['close']) for r in rows if r.get('date') and r.get('close') is not None]
        )
        con.commit()
        con.close()
    
    @staticmethod
    def get_price_cache(ticker: str) -> pd.DataFrame:
        """가격 캐시 조회"""
        DataManager.init_db()
        con = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            'SELECT date, close FROM price_cache WHERE ticker=? ORDER BY date',
            con,
            params=(ticker,)
        )
        con.close()
        return df
    
    @staticmethod
    def clear_price_cache():
        """가격 캐시 전체 삭제"""
        DataManager.init_db()
        con = sqlite3.connect(DB_PATH)
        con.execute('DELETE FROM price_cache')
        con.commit()
        con.close()
    
    @staticmethod
    def save_strategy_version(code: str, rules: RuleConfig):
        """규칙 버전 저장"""
        DataManager.init_db()
        con = sqlite3.connect(DB_PATH)
        con.execute(
            'INSERT OR REPLACE INTO strategy_version_history(strategy_code, version, effective_date, rules_json) VALUES(?, ?, ?, ?)',
            (code, rules.version, rules.effective_date or date.today().isoformat(), json.dumps(rules.to_dict(), ensure_ascii=False))
        )
        con.commit()
        con.close()
    
    @staticmethod
    def get_rules_at_date(code: str, target_date: date) -> Optional[RuleConfig]:
        """특정 날짜에 유효한 규칙 반환"""
        DataManager.init_db()
        con = sqlite3.connect(DB_PATH)
        rows = con.execute(
            'SELECT rules_json FROM strategy_version_history WHERE strategy_code=? AND effective_date<=? ORDER BY effective_date DESC LIMIT 1',
            (code, target_date.isoformat())
        ).fetchall()
        con.close()
        
        if rows:
            return RuleConfig.from_dict(json.loads(rows[0][0]))
        return None
    
    @staticmethod
    def save_snapshot(date_: date, total_value: float, composition: List[Dict], plan_text: str = ""):
        """포트폴리오 스냅샷 저장"""
        DataManager.init_db()
        con = sqlite3.connect(DB_PATH)
        con.execute(
            'INSERT INTO snapshots(date, total_value, composition_json, plan_text) VALUES(?, ?, ?, ?)',
            (date_.isoformat(), total_value, json.dumps(composition, ensure_ascii=False), plan_text)
        )
        con.commit()
        con.close()
    
    @staticmethod
    def get_snapshots(limit: Optional[int] = None) -> List[Dict]:
        """스냅샷 조회"""
        DataManager.init_db()
        con = sqlite3.connect(DB_PATH)
        query = 'SELECT date, total_value, composition_json, plan_text FROM snapshots ORDER BY date DESC'
        if limit:
            query += f' LIMIT {limit}'
        
        rows = con.execute(query).fetchall()
        con.close()
        
        result = []
        for date_, total, comp_json, plan in rows:
            result.append({
                'date': date_,
                'total': total,
                'composition': json.loads(comp_json) if comp_json else [],
                'plan': plan
            })
        return result
