"""設定檔讀寫：所有設定都存放在專案內的 config/settings.json，不會碰到系統其他地方。"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

DEFAULTS = {
    "resolution": [640, 480],          # [0, 0] = 使用相機預設；一個 Hub 接多台時建議 640x480
    "mjpg": True,
    "exclude_names": ["HD Webcam"],    # 不自動開啟的相機（名稱完全相同才排除，不分大小寫）
    "pic_folder": str(PROJECT_ROOT / "captures"),  # 命令列 preview / snap 用
}


def load_settings():
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    # 只取目前認得的欄位，舊版留下的設定（例如 left / right）直接忽略
    return {key: data.get(key, default) for key, default in DEFAULTS.items()}


def save_settings(settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
