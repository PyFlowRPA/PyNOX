"""
PyNOX — WC3 자동 재접속 매크로 (엔트리포인트)
"""
import ctypes
import os
import sys

# exe 빌드 시: src/ 를 디스크에서 import 할 수 있도록 exe 폴더를 sys.path 에 추가
if getattr(sys, "frozen", False):
    _base = os.path.dirname(sys.executable)
    if _base not in sys.path:
        sys.path.insert(0, _base)

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class _Splash(QWidget):
    _BG     = "#07070F"
    _PANEL  = "#0D0D1C"
    _BORDER = "#1C1C3A"
    _CYAN   = "#00F5FF"

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 140)

        # 중앙 패널
        panel = QWidget(self)
        panel.setGeometry(0, 0, 420, 140)
        panel.setStyleSheet(
            f"background:{self._PANEL};"
            f"border:1px solid {self._BORDER};"
            f"border-radius:6px;"
        )

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(10)

        title = QLabel("◈  PyNOX  LOADING")
        title.setStyleSheet(
            f"color:{self._CYAN};"
            f"font-family:Consolas;"
            f"font-size:15px;"
            f"font-weight:bold;"
            f"letter-spacing:4px;"
            f"border:none;background:transparent;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        self._status = QLabel("초기화 중...")
        self._status.setStyleSheet(
            "color:#666;font-family:Consolas;font-size:10px;"
            "border:none;background:transparent;"
        )
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background:{self._BG};
                border:1px solid {self._BORDER};
                border-radius:3px;
            }}
            QProgressBar::chunk {{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #005577, stop:0.7 #00CCEE, stop:1 {self._CYAN});
                border-radius:3px;
            }}
        """)
        lay.addWidget(self._bar)

        # 화면 중앙 배치
        screen = QApplication.primaryScreen().geometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )

    def set(self, value: int, msg: str):
        self._bar.setValue(value)
        self._status.setText(msg)
        QApplication.processEvents()


if __name__ == "__main__":
    if not _is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable,
            " ".join(f'"{a}"' for a in sys.argv),
            None, 1,
        )
        sys.exit()

    # ── 단일 인스턴스 체크 ──────────────────────────
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "Global\\PyNOX_SingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(
            0, "PyNOX가 이미 실행 중입니다.", "PyNOX", 0x30
        )
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    splash = _Splash()
    splash.show()
    app.processEvents()

    splash.set(5, "업데이트 확인 중...")
    try:
        from src.utils.updater import get_local_timestamp, get_local_version, fetch_latest_release, needs_update, download_and_extract, apply_update
        local_ts  = get_local_timestamp()
        remote_ver, dl_url, release_notes, published_at = fetch_latest_release()
        if needs_update(local_ts, published_at) and dl_url:
            ver_str = f"v{remote_ver}" if remote_ver else "최신"
            splash.set(10, f"업데이트 발견! ({ver_str})  다운로드 중...")
            def _on_progress(downloaded: int, total: int):
                pct = int(downloaded / total * 75) + 10   # 10 ~ 85%
                mb_d = downloaded / 1024 / 1024
                mb_t = total     / 1024 / 1024
                splash.set(pct, f"다운로드 중... {mb_d:.1f} MB / {mb_t:.1f} MB")
                app.processEvents()
            extract_dir = download_and_extract(dl_url, _on_progress)
            splash.set(90, "업데이트 적용 중... 잠시 후 재시작됩니다.")
            app.processEvents()
            apply_update(extract_dir, published_at)
            sys.exit(0)
    except Exception as _ue:
        import traceback
        ctypes.windll.user32.MessageBoxW(
            0,
            f"업데이트 중 오류 발생:\n\n{traceback.format_exc()}",
            "PyNOX 업데이트 오류",
            0x10,
        )

    splash.set(15, "설정 로드 중...")
    from src.utils.config import load_config
    from src.utils.smartkey import _smart_hook

    splash.set(40, "UI 모듈 로드 중...")
    from src.ui.main_window import MainWindow

    splash.set(75, "메인 윈도우 생성 중...")
    win = MainWindow()

    splash.set(95, "스마트키 복원 중...")
    _cfg = load_config()
    if _cfg.get("smart_key_enabled", False):
        _smart_hook.start(ord(str(_cfg.get("hero_group", 1))))
    win._on_chat_cmd_changed()
    win._on_exit_cmd_changed()

    splash.set(100, "완료")
    QTimer.singleShot(300, lambda: (splash.close(), win.show()))

    sys.exit(app.exec())
