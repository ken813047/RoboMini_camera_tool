"""相機裝置相關的共用函式（GUI 與 CLI 都會用到，不依賴 Qt）。"""

import sys
from pathlib import Path

import cv2
import numpy as np

# Windows 用 DirectShow：裝置順序和 pygrabber 列出的名稱順序一致，也支援相機屬性視窗
BACKEND = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY


def device_names():
    """回傳 DirectShow 視訊裝置名稱清單（索引即 OpenCV 的 camera index）。"""
    if sys.platform != "win32":
        return []
    try:
        from pygrabber.dshow_graph import FilterGraph

        return list(FilterGraph().get_input_devices())
    except Exception:
        return []


def list_devices(probe_max=8):
    """回傳 [(index, name), ...]。拿不到名稱時改用逐一嘗試開啟的方式。"""
    names = device_names()
    if names:
        return list(enumerate(names))
    found = []
    for i in range(probe_max):
        cap = cv2.VideoCapture(i, BACKEND)
        if cap.isOpened():
            found.append((i, f"Camera {i}"))
        cap.release()
    return found


def is_excluded(name, exclude_names):
    key = name.strip().casefold()
    return any(key == ex.strip().casefold() for ex in exclude_names)


def list_usb_cameras(exclude_names=()):
    """回傳 (要用的相機, 被排除的相機)，兩者都是 [(index, name), ...]。"""
    cams, excluded = [], []
    for idx, name in list_devices():
        (excluded if is_excluded(name, exclude_names) else cams).append((idx, name))
    return cams, excluded


def open_capture(index, width=0, height=0, fps=0, mjpg=True):
    """開啟相機並套用格式；失敗回傳 None。"""
    cap = cv2.VideoCapture(index, BACKEND)
    if not cap.isOpened():
        cap.release()
        return None
    if mjpg:
        # USB 2.0 雙目相機在高解析度下通常只有 MJPG 才跑得動
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    if width and height:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if fps:
        cap.set(cv2.CAP_PROP_FPS, fps)
    return cap


def capture_info(cap):
    return (
        int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        float(cap.get(cv2.CAP_PROP_FPS) or 0),
    )


def looks_side_by_side(width, height):
    """寬高比 >= 2.4（例如 2560x720、1280x480）通常代表左右兩顆鏡頭合併成一張。"""
    return height > 0 and width / height >= 2.4


def split_sbs(frame):
    half = frame.shape[1] // 2
    return frame[:, :half], frame[:, half : half * 2]


def save_image(path, frame):
    """cv2.imwrite 在 Windows 無法處理中文路徑，改用 imencode + tofile。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(path.suffix or ".png", np.ascontiguousarray(frame))
    if not ok:
        raise IOError(f"影像編碼失敗：{path}")
    buf.tofile(str(path))


def next_capture_number(folder):
    """依資料夾內既有檔案決定下一張的編號，避免覆蓋舊照片。"""
    folder = Path(folder)
    best = 0
    for side in ("left", "right"):
        for p in (folder / side).glob(f"{side}_*.png"):
            try:
                best = max(best, int(p.stem.split("_")[-1]))
            except ValueError:
                pass
    return best + 1
