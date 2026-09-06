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
