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
        # data_manager.py - 로컬 JSON 기반
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any
import pandas as pd
from models import StrategyConfig, RuleConfig

# 앱 실행 디렉토리
APP_DIR = Path.home() / '.asset_allocation_app'
APP_DIR.mkdir(exist_ok=True)

# JSON 파일 경로
DATA_FILE = APP_DIR / 'portfolio_data.json'
ARCHIVE_DIR = APP_DIR / 'archives'
ARCHIVE_DIR.mkdir(exist_ok=True)

class DataManager:
    """로컬 JSON 기반 데이터 관리"""
    
    @staticmethod
    def _load_json() -> Dict:
        """JSON 파일 읽기"""
        if not DATA_FILE.exists():
            return DataManager._create_default_structure()
        
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"JSON 읽기 오류: {e}")
            return DataManager._create_default_structure()
    
    @staticmethod
    def _save_json(data: Dict):
        """JSON 파일 저장"""
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            print(f"JSON 저장 오류: {e}")
    
    @staticmethod
    def _create_default_structure() -> Dict:
        """기본 구조 생성"""
        return {
            'strategies': [],
            'assets': [],
            'history': [],
            'equity': [],
            'cashflows': [],
            'benchmarks': [],
            'price_cache': {},
            'category_targets': {},
            'last_updated': datetime.now().isoformat()
        }
    
    @staticmethod
    def get_state(key: str, default=None) -> Any:
        """데이터 조회"""
        data = DataManager._load_json()
        return data.get(key, default if default is not None else {})
    
    @staticmethod
    def put_state(key: str, value: Any):
        """데이터 저장"""
        data = DataManager._load_json()
        data[key] = value
        data['last_updated'] = datetime.now().isoformat()
        DataManager._save_json(data)
    
    @staticmethod
    def get_strategies() -> List[StrategyConfig]:
        """전략 조회"""
        try:
            data = DataManager.get_state('strategies', [])
            return [StrategyConfig.from_dict(d) for d in data]
        except Exception:
            return []
    
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
    def export_json() -> bytes:
        """JSON 파일 전체 다운로드용"""
        data = DataManager._load_json()
        return json.dumps(data, ensure_ascii=False, indent=2, default=str).encode('utf-8')
    
    @staticmethod
    def import_json(json_bytes: bytes) -> bool:
        """JSON 파일 업로드 복원"""
        try:
            data = json.loads(json_bytes.decode('utf-8'))
            
            # 검증
            required_keys = ['strategies', 'history', 'assets']
            if not all(k in data for k in required_keys):
                raise ValueError('필수 항목이 없습니다')
            
            # 기존 데이터 백업
            if DATA_FILE.exists():
                backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                backup_path = ARCHIVE_DIR / backup_name
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    with open(backup_path, 'w', encoding='utf-8') as bf:
                        bf.write(f.read())
            
            # 새 데이터 저장
            data['last_updated'] = datetime.now().isoformat()
            DataManager._save_json(data)
            
            return True
        except Exception as e:
            print(f"복원 오류: {e}")
            return False
    
    @staticmethod
    def get_data_file_path() -> str:
        """데이터 파일 경로 반환"""
        return str(DATA_FILE)
    
    @staticmethod
    def get_archive_files() -> List[str]:
        """백업 파일 목록"""
        return sorted([f.name for f in ARCHIVE_DIR.glob('backup_*.json')], reverse=True)
    
    @staticmethod
    def restore_from_archive(filename: str) -> bool:
        """백업에서 복원"""
        backup_path = ARCHIVE_DIR / filename
        if not backup_path.exists():
            return False
        
        try:
            with open(backup_path, 'rb') as f:
                return DataManager.import_json(f.read())
        except Exception:
            return False

