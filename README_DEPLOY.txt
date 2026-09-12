[중요] Streamlit 배포 방법

1. 이 폴더의 5개 파일을 같은 GitHub 저장소/폴더에 올립니다.
   - asset_allocation_app.py
   - strategy_engine.py
   - strategy_spec.json
   - requirements.txt
   - test_regression.py (선택: 테스트용)

2. Streamlit Cloud의 Main file path는 반드시:
   asset_allocation_app.py

3. strategy_engine.py와 strategy_spec.json은 asset_allocation_app.py와 같은 폴더에 있어야 합니다.

4. 기존에 asset_allocation_app_v15.py만 올려 실행했다면 ModuleNotFoundError가 발생합니다.

5. 저장소의 실제 구조 예:
   portfolio-rabal/
   ├─ asset_allocation_app.py
   ├─ strategy_engine.py
   ├─ strategy_spec.json
   └─ requirements.txt

주의: strategy_engine_v15.py / strategy_spec_v15.json이라는 파일명을 그대로 써도 안 됩니다. 앱은 strategy_engine이라는 모듈과 strategy_spec.json을 찾습니다. 따라서 배포본에서는 이름을 위와 같이 맞췄습니다.
