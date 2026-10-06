"""命令列介面。

    python -m stereocam gui                       開啟圖形介面（預設）
    python -m stereocam list [--probe]            列出相機裝置
    python -m stereocam preview --left 0 --right 1
    python -m stereocam preview --sbs 0 --width 2560 --height 720
    python -m stereocam snap --left 0 --right 1 --count 10 --interval 1
"""

import argparse
import time
from datetime import datetime
from pathlib import Path

from . import __version__, devices
from .config import load_settings


def cmd_list(args):
    devs = devices.list_devices()
    if not devs:
        print("找不到任何相機。請確認 USB 已插好，並關閉 Windows「相機」App。")
        return 1
    exclude = load_settings()["exclude_names"]
    print(f"找到 {len(devs)} 個視訊裝置（排除清單：{', '.join(exclude) or '無'}）：")
    cam_no = 0
    for idx, name in devs:
        if devices.is_excluded(name, exclude):
            tag = "排除 "
        else:
            cam_no += 1
            tag = f"CAM {cam_no}"
        line = f"  {tag}  [{idx}] {name}"
        if args.probe:
            cap = devices.open_capture(idx, mjpg=False)
            if cap is None:
                line += "  -> 無法開啟（可能被其他程式佔用）"
            else:
                ok, frame = cap.read()
                w, h, fps = devices.capture_info(cap)
                cap.release()
                line += f"  -> 預設 {w}x{h}" + (f" @ {fps:.0f}fps" if fps > 0 else "") + ("" if ok else "（讀不到影像）")
        print(line)
    if not args.probe:
        print("\n加上 --probe 可以順便測試每個裝置的預設解析度。")
    return 0


def _open_pair(args):
    """依參數開啟相機，回傳 (caps, reader)；reader() 回傳 (left, right) 影像或 None。"""
    if args.sbs is not None:
        cap = devices.open_capture(args.sbs, args.width, args.height, args.fps, not args.no_mjpg)
        if cap is None:
            raise SystemExit(f"無法開啟相機 #{args.sbs}")

        def read():
            ok, frame = cap.read()
            return devices.split_sbs(frame) if ok else None

        return [cap], read

    caps = []
    for idx in (args.left, args.right):
        cap = devices.open_capture(idx, args.width, args.height, args.fps, not args.no_mjpg)
        if cap is None:
            for c in caps:
                c.release()
            raise SystemExit(f"無法開啟相機 #{idx}")
        caps.append(cap)

    def read():
        # 先 grab 兩台再 retrieve，讓左右影像時間盡量接近
        if not (caps[0].grab() and caps[1].grab()):
            return None
        ok1, left = caps[0].retrieve()
        ok2, right = caps[1].retrieve()
        return (left, right) if ok1 and ok2 else None

    return caps, read


def _save_pair(folder, pair):
    n = devices.next_capture_number(folder)
    for side, frame in zip(("left", "right"), pair):
        devices.save_image(Path(folder) / side / f"{side}_{n:04d}.png", frame)
    return n


def cmd_preview(args):
    import cv2
    import numpy as np

    caps, read = _open_pair(args)
    print("預覽中：按 Space 拍照、按 q 或 Esc 離開")
    try:
        while True:
            pair = read()
            if pair is None:
                time.sleep(0.01)
                continue
            left, right = pair
            if left.shape[0] != right.shape[0]:
                right = cv2.resize(right, (right.shape[1] * left.shape[0] // right.shape[0], left.shape[0]))
            view = np.hstack([left, right])
            if view.shape[1] > 1600:
                scale = 1600 / view.shape[1]
                view = cv2.resize(view, None, fx=scale, fy=scale)
            cv2.imshow("StereoCam preview (Space=capture, q=quit)", view)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == 32:
                n = _save_pair(args.out, pair)
                print(f"已存第 {n} 組 -> {args.out}")
    finally:
        for c in caps:
            c.release()
        cv2.destroyAllWindows()
    return 0


def cmd_snap(args):
    caps, read = _open_pair(args)
    try:
        # 丟掉前幾張，等自動曝光穩定
        for _ in range(10):
            read()
        for i in range(args.count):
            pair = read()
            if pair is None:
                print("讀取失敗，略過")
                continue
            n = _save_pair(args.out, pair)
            print(f"[{datetime.now():%H:%M:%S}] 已存第 {n} 組")
            if i + 1 < args.count:
                time.sleep(args.interval)
    finally:
        for c in caps:
            c.release()
    print(f"完成，存放於 {Path(args.out).resolve()}")
    return 0


def cmd_gui(_args):
    from .gui import run

    return run()


def _add_cam_args(p, default_out):
    p.add_argument("--left", type=int, default=0, help="左相機 index（雙裝置模式）")
    p.add_argument("--right", type=int, default=1, help="右相機 index（雙裝置模式）")
    p.add_argument("--sbs", type=int, metavar="INDEX", help="單一裝置左右合併輸出模式，指定該裝置 index")
    p.add_argument("--width", type=int, default=0, help="要求的影像寬度（SBS 模式為合併後寬度）")
    p.add_argument("--height", type=int, default=0)
    p.add_argument("--fps", type=float, default=0)
    p.add_argument("--no-mjpg", action="store_true", help="不要強制 MJPG 格式")
    p.add_argument("--out", default=default_out, help="照片存放資料夾")


def main(argv=None):
    default_out = load_settings()["pic_folder"]
    parser = argparse.ArgumentParser(prog="stereocam", description="雙目 USB 相機工具")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("gui", help="開啟圖形介面（預設）")
    p_list = sub.add_parser("list", help="列出相機裝置")
    p_list.add_argument("--probe", action="store_true", help="逐一開啟裝置並顯示預設解析度")
    p_prev = sub.add_parser("preview", help="用 OpenCV 視窗快速預覽左右畫面")
    _add_cam_args(p_prev, default_out)
    p_snap = sub.add_parser("snap", help="不開視窗，連續拍下 N 組左右照片")
    _add_cam_args(p_snap, default_out)
    p_snap.add_argument("--count", type=int, default=1)
    p_snap.add_argument("--interval", type=float, default=1.0, help="每組間隔秒數")

    args = parser.parse_args(argv)
    handlers = {None: cmd_gui, "gui": cmd_gui, "list": cmd_list, "preview": cmd_preview, "snap": cmd_snap}
    return handlers[args.cmd](args)
