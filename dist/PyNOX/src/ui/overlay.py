"""
ui/overlay.py — 이미지 서치 감지 위치 오버레이
"""
import ctypes
import ctypes.wintypes

from PySide6.QtCore import Qt, QRect, QPoint, QTimer
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QApplication, QWidget

from src.utils.process import find_war3_hwnd


class OverlayWindow(QWidget):
    """이미지 서치 감지 위치에 반투명 사각형 + 십자선을 그리는 전체화면 오버레이."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._match_rect: "QRect | None" = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._clear)

    def show_match(self, client_x: int, client_y: int, tw: int, th: int):
        """클라이언트 좌표 → 스크린 좌표 변환 후 오버레이 표시."""
        hwnd = find_war3_hwnd()
        if not hwnd:
            return
        pt = ctypes.wintypes.POINT(client_x, client_y)
        ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
        target_screen = QApplication.screenAt(QPoint(pt.x, pt.y))
        if target_screen is None:
            target_screen = QApplication.primaryScreen()
        screen = target_screen.geometry()
        self.setGeometry(screen)
        pad = 6
        self._match_rect = QRect(
            pt.x - tw // 2 - pad,
            pt.y - th // 2 - pad,
            tw + pad * 2,
            th + pad * 2,
        )
        self._hide_timer.stop()
        self._hide_timer.start(800)
        self.show()
        self.raise_()
        self.update()

    def _clear(self):
        self._match_rect = None
        self.hide()

    def clear(self):
        self._hide_timer.stop()
        self._clear()

    def paintEvent(self, _):
        if not self._match_rect:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r  = self._match_rect
        cx = r.center().x()
        cy = r.center().y()
        p.fillRect(r, QColor(166, 227, 161, 45))
        p.setPen(QPen(QColor(166, 227, 161), 2))
        p.drawRect(r)
        corner = 10
        p.setPen(QPen(QColor(166, 227, 161), 3))
        for ox, oy, dx, dy in [
            (r.left(),  r.top(),     1,  1),
            (r.right(), r.top(),    -1,  1),
            (r.left(),  r.bottom(),  1, -1),
            (r.right(), r.bottom(), -1, -1),
        ]:
            p.drawLine(ox, oy, ox + dx * corner, oy)
            p.drawLine(ox, oy, ox, oy + dy * corner)
        p.setPen(QPen(QColor(166, 227, 161, 200), 1))
        p.drawLine(cx - 12, cy, cx + 12, cy)
        p.drawLine(cx, cy - 12, cx, cy + 12)
