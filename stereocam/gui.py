"""StereoCam 圖形介面（PySide6）。

啟動時自動偵測 USB 相機（排除 config/settings.json 的 exclude_names，例如筆電內建的 HD Webcam），
依序放進 CAM 1 ~ CAM 6 並直接開啟。

每顆相機在自己的 QThread 裡讀影像，只保留最新一張；GUI 用 QTimer 取最新影像來畫，
所以畫面再忙也不會累積延遲。
"""

import queue
import sys
import threading
import time

import cv2
from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import __version__, devices
from .config import load_settings, save_settings

MAX_CAMERAS = 6
GRID_COLUMNS = 3
OPEN_GAP_MS = 200  # 一台開好之後隔多久再開下一台；同時開太多台容易搶 USB 頻寬失敗

RESOLUTIONS = [
    ("相機預設", 0, 0),
    ("320 x 240", 320, 240),
    ("640 x 480", 640, 480),
    ("1280 x 720", 1280, 720),
    ("1920 x 1080", 1920, 1080),
]

STYLE = """
QWidget { font-family: "Segoe UI", "Microsoft JhengHei UI"; font-size: 10pt; }
QGroupBox { font-weight: bold; border: 1px solid #c8c8c8; border-radius: 4px; margin-top: 14px; padding: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QLabel#Header { font-size: 12pt; font-weight: bold; background: #f0f0f0; border: 1px solid #c8c8c8; padding: 3px; }
QLabel#Live { font-size: 11pt; font-weight: bold; color: #888; }
QLabel#Live[on="true"] { color: #d00000; }
QPushButton#Tool { font-size: 12pt; min-width: 40px; min-height: 26px; }
"""


# --------------------------------------------------------------------------- camera thread
class CameraWorker(QThread):
    opened = Signal(int, str)        # slot, 描述文字
    failed = Signal(int, str)        # slot, 錯誤訊息
    closed = Signal(int, object)     # slot, worker 本身

    def __init__(self, slot, index, width, height, mjpg, parent=None):
        super().__init__(parent)
        self.slot = slot
        self.index = index
        self.width = width
        self.height = height
        self.mjpg = mjpg
        self.measured_fps = 0.0
        self._lock = threading.Lock()
        self._frame = None
        self._seq = 0
        self._cmds = queue.SimpleQueue()
        self._stop = threading.Event()

    def latest(self):
        with self._lock:
            return self._seq, self._frame

    def show_driver_settings(self):
        self._cmds.put((cv2.CAP_PROP_SETTINGS, 1))

    def request_stop(self):
        self._stop.set()

    def stop(self):
        self._stop.set()
        self.wait(3000)

    def run(self):
        cap = devices.open_capture(self.index, self.width, self.height, 0, self.mjpg)
        if cap is None:
            self.failed.emit(self.slot, "無法開啟\n可能被其他程式佔用，或 USB 頻寬不足")
            self.closed.emit(self.slot, self)
            return
        try:
            w, h, _ = devices.capture_info(cap)
            self.opened.emit(self.slot, f"{w}x{h}")
            fails, count, t0 = 0, 0, time.perf_counter()
            while not self._stop.is_set():
                while True:
                    try:
                        prop, value = self._cmds.get_nowait()
                    except queue.Empty:
                        break
                    cap.set(prop, value)
                ok, frame = cap.read()
                if not ok or frame is None:
                    fails += 1
                    if fails >= 50:
                        self.failed.emit(self.slot, "讀不到影像\n可能被拔除、被佔用，或 USB 頻寬不足")
                        break
                    self.msleep(20)
                    continue
                fails = 0
                with self._lock:
                    self._frame = frame
                    self._seq += 1
                count += 1
                now = time.perf_counter()
                if now - t0 >= 1.0:
                    self.measured_fps = count / (now - t0)
                    count, t0 = 0, now
        finally:
            cap.release()
            self.closed.emit(self.slot, self)


# --------------------------------------------------------------------------- widgets
class VideoView(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(240, 180)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setStyleSheet("background:#000; color:#777; font-size:13pt; border:1px solid #888;")

    def show_frame(self, bgr):
        h, w = bgr.shape[:2]
        area = self.contentsRect()
        scale = min(area.width() / w, area.height() / h)
        if scale <= 0:
            return
        tw, th = max(1, int(w * scale)), max(1, int(h * scale))
        small = cv2.resize(bgr, (tw, th), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        self.setPixmap(QPixmap.fromImage(QImage(rgb.data, tw, th, rgb.strides[0], QImage.Format_RGB888)))

    def show_text(self, text):
        self.clear()
        self.setText(text)


class CameraPanel(QFrame):
    def __init__(self, number):
        super().__init__()
        self.number = number
        self.device = None  # (index, name)
        self.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)

        header = QLabel(f"CAM {number}")
        header.setObjectName("Header")
        header.setAlignment(Qt.AlignCenter)
        v.addWidget(header)

        live_row = QHBoxLayout()
        self.live = QLabel("LIVE")
        self.live.setObjectName("Live")
        self.info = QLabel()
        self.info.setStyleSheet("color:#555;")
        live_row.addWidget(self.live)
        live_row.addStretch()
        live_row.addWidget(self.info)
        v.addLayout(live_row)

        self.view = VideoView()
        v.addWidget(self.view, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_play = self._tool_button("▶", "開啟相機")
        self.btn_stop = self._tool_button("■", "關閉相機")
        self.btn_settings = self._tool_button("⚙", "開啟驅動程式的相機屬性視窗（曝光、亮度、白平衡…）")
        for b in (self.btn_play, self.btn_stop, self.btn_settings):
            btn_row.addWidget(b)
        v.addLayout(btn_row)
        self.set_running(False)

    @staticmethod
    def _tool_button(text, tip):
        b = QPushButton(text)
        b.setObjectName("Tool")
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.NoFocus)
        return b

    def device_label(self):
        if self.device is None:
            return ""
        idx, name = self.device
        return f"{name} (#{idx})"

    def assign(self, device):
        self.device = device
        self.set_running(False)

    def set_running(self, running, message=None):
        has_device = self.device is not None
        self.btn_play.setEnabled(has_device and not running)
        self.btn_stop.setEnabled(running)
        self.btn_settings.setEnabled(running)
        self.live.setProperty("on", "true" if running else "false")
        self.live.style().unpolish(self.live)
        self.live.style().polish(self.live)
        if not running:
            if not has_device:
                self.info.setText("未連接")
                self.view.show_text("未連接")
            else:
                self.info.setText(f"{self.device_label()}  {'開啟失敗' if message else '未開啟'}")
                self.view.show_text(message or "NO SIGNAL")


# --------------------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"RoboMini_camera_QC {__version__}")
        self.resize(1600, 1000)
        self.settings = load_settings()
        self.panels = [CameraPanel(i + 1) for i in range(MAX_CAMERAS)]
        self.workers = [None] * MAX_CAMERAS
        self.last_seq = [-1] * MAX_CAMERAS
        self.frame_size = [None] * MAX_CAMERAS
        self.errors = [None] * MAX_CAMERAS
        self._pending = []  # 等待依序開啟的 slot
        self._last_info = 0.0

        tabs = QTabWidget()
        tabs.addTab(self._build_main_tab(), "Main Control")
        tabs.addTab(self._build_help_tab(), "說明")
        self.setCentralWidget(tabs)
        self._load_ui_settings()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(15)
        # 視窗出現後馬上自動偵測並開啟所有 USB 相機
        QTimer.singleShot(0, self.detect_and_open)

    # ---------------- UI construction
    def _build_main_tab(self):
        page = QWidget()
        root = QVBoxLayout(page)

        control = QGroupBox("Control")
        row = QHBoxLayout(control)
        row.addWidget(QLabel("解析度:"))
        self.res_combo = QComboBox()
        for label, w, h in RESOLUTIONS:
            self.res_combo.addItem(label, (w, h))
        row.addWidget(self.res_combo)
        self.mjpg_check = QCheckBox("MJPG")
        self.mjpg_check.setToolTip("多台相機共用一個 USB Hub 時建議開啟，可大幅降低頻寬")
        row.addWidget(self.mjpg_check)
        for text, slot in (("重新偵測相機", self.detect_and_open), ("全部開啟", self.open_all), ("全部關閉", self.stop_all)):
            b = QPushButton(text)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addSpacing(16)
        self.summary = QLabel("偵測中…")
        row.addWidget(self.summary)
        row.addStretch()
        root.addWidget(control)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, panel in enumerate(self.panels):
            grid.addWidget(panel, i // GRID_COLUMNS, i % GRID_COLUMNS)
            panel.btn_play.clicked.connect(lambda _=False, s=i: self.start_slot(s))
            panel.btn_stop.clicked.connect(lambda _=False, s=i: self.stop_slot(s))
            panel.btn_settings.clicked.connect(lambda _=False, s=i: self._driver_settings(s))
        for c in range(GRID_COLUMNS):
            grid.setColumnStretch(c, 1)
        for r in range((MAX_CAMERAS + GRID_COLUMNS - 1) // GRID_COLUMNS):
            grid.setRowStretch(r, 1)
        root.addWidget(grid_host, 1)
        return page

    def _build_help_tab(self):
        tb = QTextBrowser()
        tb.setHtml(
            f"""
<h2>使用說明</h2>
<ol>
<li><b>先關閉 Windows「相機」App</b>：同一顆 USB 相機一次只能被一個程式使用。</li>
<li>啟動時會自動偵測所有 USB 相機，依 Windows 列出的順序放進 CAM 1 ~ CAM {MAX_CAMERAS} 並直接開啟。</li>
<li>不想自動開啟的相機（例如筆電內建的 HD Webcam）寫在 <code>config/settings.json</code> 的
    <code>exclude_names</code>，名稱要完全相同（不分大小寫）。</li>
<li>插拔相機後按「重新偵測相機」。編號跟著 Windows 的裝置順序走，換 USB 孔或重新插拔後順序可能會變。</li>
<li>按 <b>▶</b> 開啟、<b>■</b> 關閉、<b>⚙</b> 開啟驅動程式內建的屬性視窗（曝光、亮度、白平衡等）。</li>
<li>一個 USB Hub 接很多台時，如果有幾台顯示「無法開啟」或「讀不到影像」，通常是 USB 頻寬不夠：
    勾選 MJPG、把解析度降到 640x480 或 320x240，或改用 USB 3.0 Hub / 分散到不同的 USB 孔。</li>
</ol>
<p>解析度和 MJPG 設定會在關閉視窗時存到 <code>config/settings.json</code>。</p>
"""
        )
        return tb

    # ---------------- settings
    def _load_ui_settings(self):
        s = self.settings
        self.res_combo.setCurrentIndex(max(0, self.res_combo.findData(tuple(s["resolution"]))))
        self.mjpg_check.setChecked(bool(s["mjpg"]))

    def _save_ui_settings(self):
        self.settings["resolution"] = list(self.res_combo.currentData())
        self.settings["mjpg"] = self.mjpg_check.isChecked()
        try:
            save_settings(self.settings)
        except OSError as e:
            print(f"無法儲存設定：{e}", file=sys.stderr)

    def _update_controls(self):
        idle = not any(self.workers)
        self.res_combo.setEnabled(idle)
        self.mjpg_check.setEnabled(idle)

    # ---------------- camera control
    @Slot()
    def detect_and_open(self):
        self.stop_all()
        exclude = self.settings["exclude_names"]
        cams, excluded = devices.list_usb_cameras(exclude)
        shown, extra = cams[:MAX_CAMERAS], cams[MAX_CAMERAS:]
        for i, panel in enumerate(self.panels):
            panel.assign(shown[i] if i < len(shown) else None)

        msg = f"偵測到 {len(shown)} 台 USB 相機"
        if excluded:
            msg += f"（已排除：{', '.join(name for _, name in excluded)}）"
        if extra:
            msg += f"；超過 {MAX_CAMERAS} 台，另外 {len(extra)} 台未顯示"
        self.summary.setText(msg)
        if not shown:
            self.statusBar().showMessage("找不到 USB 相機。請確認 USB 連接、關閉 Windows「相機」App，再按「重新偵測相機」。")
            return
        self.open_all()

    @Slot()
    def open_all(self):
        self._pending = [s for s, p in enumerate(self.panels) if p.device and not self.workers[s]]
        self._open_next()

    def _open_next(self):
        # 一次只開一台：等這台 opened / failed 之後才開下一台
        while self._pending:
            if self.start_slot(self._pending.pop(0)):
                return

    def start_slot(self, slot):
        panel = self.panels[slot]
        if panel.device is None or self.workers[slot]:
            return False
        idx, _ = panel.device
        w, h = self.res_combo.currentData()
        worker = CameraWorker(slot, idx, w, h, self.mjpg_check.isChecked(), self)
        worker.opened.connect(self._on_opened)
        worker.failed.connect(self._on_failed)
        worker.closed.connect(self._on_closed)
        self.workers[slot] = worker
        self.last_seq[slot] = -1
        self.frame_size[slot] = None
        self.errors[slot] = None
        worker.start()
        panel.set_running(True)
        panel.info.setText(f"{panel.device_label()}  開啟中…")
        panel.view.show_text("開啟中…")
        self._update_controls()
        self.statusBar().showMessage(f"正在開啟 CAM {slot + 1} …")
        return True

    def stop_slot(self, slot):
        worker = self.workers[slot]
        if not worker:
            return
        self.workers[slot] = None
        worker.stop()
        self.panels[slot].set_running(False)
        self._update_controls()

    @Slot()
    def stop_all(self):
        self._pending = []
        running = [w for w in self.workers if w]
        for w in running:  # 先全部通知停止，再一起等，關得比較快
            w.request_stop()
        for w in running:
            w.wait(3000)
        self.workers = [None] * MAX_CAMERAS
        for panel in self.panels:
            panel.set_running(False)
        self._update_controls()

    def _driver_settings(self, slot):
        worker = self.workers[slot]
        if worker:
            worker.show_driver_settings()

    @Slot(int, str)
    def _on_opened(self, slot, info):
        self.statusBar().showMessage(f"CAM {slot + 1} 已開啟：{info}")
        QTimer.singleShot(OPEN_GAP_MS, self._open_next)

    @Slot(int, str)
    def _on_failed(self, slot, msg):
        self.errors[slot] = msg
        self.statusBar().showMessage(f"CAM {slot + 1}：{msg.splitlines()[0]}")
        QTimer.singleShot(OPEN_GAP_MS, self._open_next)

    @Slot(int, object)
    def _on_closed(self, slot, worker):
        if self.workers[slot] is worker:  # 不是使用者按的關閉（錯誤 / 拔線）
            self.workers[slot] = None
            self.panels[slot].set_running(False, self.errors[slot])
            self._update_controls()

    # ---------------- rendering
    def _tick(self):
        for slot, worker in enumerate(self.workers):
            if not worker:
                continue
            seq, frame = worker.latest()
            if frame is not None and seq != self.last_seq[slot]:
                self.last_seq[slot] = seq
                self.frame_size[slot] = (frame.shape[1], frame.shape[0])
                self.panels[slot].view.show_frame(frame)

        now = time.perf_counter()
        if now - self._last_info > 0.5:
            self._last_info = now
            for slot, worker in enumerate(self.workers):
                size = self.frame_size[slot]
                if worker and size:
                    panel = self.panels[slot]
                    panel.info.setText(f"{panel.device_label()}  {size[0]}x{size[1]}  {worker.measured_fps:.1f} fps")

    # ---------------- events
    def closeEvent(self, event):
        self.timer.stop()
        self.stop_all()
        self._save_ui_settings()
        super().closeEvent(event)


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    return app.exec()
