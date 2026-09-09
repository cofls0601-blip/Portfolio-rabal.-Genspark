import ast
from pathlib import Path

APP = Path(__file__).with_name("asset_allocation_app.py")
src = APP.read_text(encoding="utf-8")
tree = ast.parse(src)

# 이전에 반복된 Streamlit dynamic-import 오류와 직접 연관된 네이티브 위젯은 사용하지 않는다.
forbidden = ["st.date_input", "st.file_uploader", "st.download_button"]
for name in forbidden:
    assert name not in src, f"forbidden widget remains: {name}"

# 외부 CDN 폰트도 사용하지 않는다.
assert "jsdelivr" not in src.lower()
assert "axios" not in src.lower()

# 구버전 account_cash가 없어도 ensure_cash_rows가 None.get으로 죽지 않도록 방어 코드가 있어야 한다.
assert "if not isinstance(legacy_cash, dict): legacy_cash = {}" in src

# KV 상태 누락/손상 복구 코드가 존재해야 한다.
assert "kv_quarantine" in src
assert "def _state_default" in src

print("STABILITY_STATIC_RESULT: ALL_PASS")
