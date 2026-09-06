# price_fetcher.py
import pandas as pd
import requests
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from data_manager import DataManager

YAHOO_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

class PriceFetcher:
    """가격 조회 (KRX, 공공데이터포털, Yahoo)"""
    
    @staticmethod
    def fetch_yahoo_day(symbol: str, day: str) -> Optional[Dict]:
        """Yahoo에서 특정 일자 종가 조회"""
        try:
            end = pd.Timestamp(day) + timedelta(days=2)
            start = end - timedelta(days=12)
            
            url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
            r = requests.get(
                url,
                params={
                    'period1': int(start.timestamp()),
                    'period2': int(end.timestamp()),
                    'interval': '1d'
                },
                headers=YAHOO_HEADERS,
                timeout=15
            )
            r.raise_for_status()
            
            result = (r.json().get('chart') or {}).get('result')
            if not result:
                return None
            
            result = result[0]
            ts = result.get('timestamp') or []
            closes = ((result.get('indicators') or {}).get('quote') or [{}])[0].get('close') or []
            
            for t, c in zip(ts, closes):
                if c is None:
                    continue
                row_date = pd.Timestamp(t, unit='s').strftime('%Y%m%d')
                if row_date <= pd.Timestamp(day).strftime('%Y%m%d'):
                    return {'date': row_date, 'close': float(c), 'symbol': symbol}
            
            return None
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            return None
    
    @staticmethod
    def fetch_yahoo_monthly(symbol: str, day: str) -> pd.DataFrame:
        """Yahoo에서 13개월 월별 데이터 조회"""
        try:
            end = pd.Timestamp(day) + timedelta(days=2)
            start = end - timedelta(days=430)
            
            url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
            r = requests.get(
                url,
                params={
                    'period1': int(start.timestamp()),
                    'period2': int(end.timestamp()),
                    'interval': '1mo'
                },
                headers=YAHOO_HEADERS,
                timeout=15
            )
            r.raise_for_status()
            
            result = (r.json().get('chart') or {}).get('result')
            if not result:
                return pd.DataFrame()
            
            result = result[0]
            ts = result.get('timestamp') or []
            closes = ((result.get('indicators') or {}).get('quote') or [{}])[0].get('close') or []
            
            rows = []
            for t, c in zip(ts, closes):
                if c is not None:
                    rows.append({
                        'date': pd.Timestamp(t, unit='s').strftime('%Y%m%d'),
                        'close': float(c),
                        'symbol': symbol
                    })
            
            return pd.DataFrame(rows)
        except Exception:
            return pd.DataFrame()
    
    @staticmethod
    def fetch_usd_krw() -> Optional[float]:
        """USD/KRW 환율 조회"""
        try:
            day = pd.Timestamp.now().strftime('%Y-%m-%d')
            end = pd.Timestamp(day) + timedelta(days=2)
            start = end - timedelta(days=10)
            
            url = 'https://query1.finance.yahoo.com/v8/finance/chart/KRW=X'
            r = requests.get(
                url,
                params={
                    'period1': int(start.timestamp()),
                    'period2': int(end.timestamp()),
                    'interval': '1d'
                },
                headers=YAHOO_HEADERS,
                timeout=15
            )
            r.raise_for_status()
            
            result = (r.json().get('chart') or {}).get('result')
            if not result:
                return None
            
            closes = ((result[0].get('indicators') or {}).get('quote') or [{}])[0].get('close') or []
            if closes:
                rate = float([c for c in closes if c is not None][-1])
                DataManager.put_state('last_fx_rate', {
                    'rate': rate,
                    'date': pd.Timestamp.now().isoformat()
                })
                return rate
        except Exception:
            pass
        
        # Fallback: 마지막 성공한 환율
        try:
            cached = DataManager.get_state('last_fx_rate', {})
            return cached.get('rate')
        except Exception:
            return None
