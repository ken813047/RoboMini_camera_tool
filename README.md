# RoboMini_camera_QC — 多台 USB 相機即時預覽（最多 6 台）

## 快速開始

1. 用 USB Hub 接上相機，**關閉 Windows「相機」App**（同一顆相機一次只能被一個程式使用）。
2. 雙擊 **`RoboMini_camera_QC.bat`**：
   - 自動偵測所有 USB 相機，排除筆電內建的 `HD Webcam`，依序放進 CAM 1 ~ CAM 6 並直接開啟。
   - 第一次會自動在專案內建立 `.venv` 並安裝套件（需要網路），之後再雙擊就會直接開啟。

## 檔案

| 檔案 | 用途 |
|---|---|
| `RoboMini_camera_QC.bat` | 雙擊開啟圖形介面 |
| `ListCameras.bat` | 列出所有相機、對應的 CAM 編號、哪些被排除 |
| `CLI.bat` | 開啟一個已經進入獨立環境的命令列視窗 |
| `scripts/env.bat` | 建立 / 檢查獨立環境（其他 bat 會自動呼叫） |
| `stereocam/` | Python 原始碼（`gui.py` 介面、`cli.py` 命令列、`devices.py` 相機函式） |
| `config/settings.json` | 設定檔（關閉視窗時自動儲存） |

## 設定（`config/settings.json`）

```json
{
  "resolution": [640, 480],
  "mjpg": true,
  "exclude_names": ["HD Webcam"]
}
```

- `exclude_names`：不要自動開啟的相機名稱，名稱要完全相同（不分大小寫）。名稱可以從 `ListCameras.bat` 看。
- `resolution`：`[0, 0]` 表示用相機預設。

## 6 台相機共用一個 USB Hub

- CAM 編號跟著 Windows 的裝置順序走，換 USB 孔或重新插拔後順序可能會變。
- 如果有幾台顯示「無法開啟」或「讀不到影像」，通常是 USB 頻寬不夠：
  勾選 MJPG、把解析度降到 640x480 或 320x240，或改用 USB 3.0 Hub / 分散到不同的 USB 孔。
- 程式會一台開好再開下一台，避免同時搶頻寬。

## 獨立環境

- 所有套件都裝在專案內的 `.venv`，不會動到系統 Python 或其他專案。
- `scripts/env.bat` 會清掉 `PYTHONPATH`、`PYTHONHOME` 等外部變數，並設定 `PYTHONNOUSERSITE=1`。
- 修改 `requirements.txt` 後，下次執行 bat 會自動重新安裝。
- 想整個重來：刪掉 `.venv` 資料夾再雙擊 `RoboMini_camera_QC.bat`。

## 命令列

```bat
python -m stereocam list --probe
python -m stereocam preview --left 0 --right 1
python -m stereocam snap --left 0 --right 1 --count 10 --interval 1
```
