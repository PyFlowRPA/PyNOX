"""
ui/main_window.py — MainWindow 및 UI 지원 클래스
"""
import ctypes
import ctypes.wintypes
import os
import sys
import threading
import time

import mss
import numpy as np
import psutil

from PySide6.QtCore import Qt, QObject, QPoint, QPointF, QRect, QSize, QTimer, QThread, Signal
from PySide6.QtGui import (
    QColor, QCursor, QEnterEvent, QFont, QImage, QMouseEvent, QPainter, QPen, QPixmap,
    QTextCharFormat, QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QPushButton, QRadioButton, QRubberBand, QScrollArea, QSizePolicy, QSpinBox,
    QStyle, QStyledItemDelegate, QStyleOptionButton, QStyleOptionViewItem, QStylePainter,
    QMessageBox, QTabWidget, QTextEdit, QVBoxLayout, QWidget, QWidgetAction,
)

from src.ui.theme import (
    DARK_BG, DARK_PANEL, DARK_BORDER,
    ACCENT, ACCENT_H, TEXT, TEXT_DIM,
    GREEN, RED, YELLOW,
)
from src.ui.overlay import OverlayWindow
from src.ui.portal_widget import PORTAL_CONFIGS, PortalZoneWidget, PortalBossPanel
from src.ui.widgets import ConfigSpinBox, ConfigCheckBox
from src.utils.config import load_config, save_config, update_config, update_config_multi
from src.utils.process import find_war3_hwnd
from src.utils.smartkey import _smart_hook
from src.utils.ocr import _kor_available, ocr_text as _ocr_text
from src.utils.memory import write_game_delay, patch_war3_preferences, patch_war3_resolution_registry
from src.core.image_match import _image_match, image_exists, _CHAR_IMAGES, _resource_path
from src.core.input import _user32, _press_vk, click_image_center, _scale_coords
from src.core.capture import _get_pixel_at_client, _capture_war3_bgr, _get_cursor_client, _get_pixel_at_cursor
from src.macro.worker import WatchWorker

from datetime import datetime
def now():
    return datetime.now().strftime("%H:%M:%S")


class _NoxSignals(QObject):
    log_sig    = Signal(str, str)
    update_sig = Signal(str, str)
    status_sig = Signal(str, str)

from src.utils.crypto import encrypt_password, decrypt_password

# ── 핫키 매핑 ────────────────────────────────────────────────────
try:
    from pynput import keyboard as _kb
    _HAS_PYNPUT = True
except ImportError:
    _HAS_PYNPUT = False
_PYNPUT_OK = _HAS_PYNPUT

_ALL_KEYS = [
    "F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12",
    "Escape","Print Screen","Scroll Lock","Pause",
    "Insert","Delete","Home","End","Page Up","Page Down",
    "Arrow Up","Arrow Down","Arrow Left","Arrow Right",
    "Num Lock","Slash / ?","Num /","Num *","Minus - _","Num -","Num +",
    "Period . >","Num .","Enter","Num Enter",
    "0","1","2","3","4","5","6","7","8","9",
    "Num 0","Num 1","Num 2","Num 3","Num 4","Num 5",
    "Num 6","Num 7","Num 8","Num 9",
    "Backtick ` ~","Equal = +","Backspace","Caps Lock","Tab","Space",
    "Ctrl","Alt","Shift","Menu",
    "A","B","C","D","E","F","G","H","I","J","K","L","M",
    "N","O","P","Q","R","S","T","U","V","W","X","Y","Z",
    "Left Bracket [ {","Right Bracket ] }","Backslash \\ |",
    "Semicolon ; :","Apostrophe ' \"","Comma , <",
]

_KEY_NAME_TO_VK: dict = {
    # 기능키
    "F1":0x70,"F2":0x71,"F3":0x72,"F4":0x73,"F5":0x74,"F6":0x75,
    "F7":0x76,"F8":0x77,"F9":0x78,"F10":0x79,"F11":0x7A,"F12":0x7B,
    # 특수키
    "Escape":0x1B,"Print Screen":0x2C,"Scroll Lock":0x91,"Pause":0x13,
    "Insert":0x2D,"Delete":0x2E,"Home":0x24,"End":0x23,
    "Page Up":0x21,"Page Down":0x22,
    "Arrow Up":0x26,"Arrow Down":0x28,"Arrow Left":0x25,"Arrow Right":0x27,
    # 편집키
    "Backspace":0x08,"Tab":0x09,"Caps Lock":0x14,"Enter":0x0D,"Space":0x20,
    # 보조키
    "Ctrl":0x11,"Alt":0x12,"Shift":0x10,"Menu":0x5D,
    # 숫자키 (키보드 상단)
    "0":0x30,"1":0x31,"2":0x32,"3":0x33,"4":0x34,
    "5":0x35,"6":0x36,"7":0x37,"8":0x38,"9":0x39,
    # 알파벳
    "A":0x41,"B":0x42,"C":0x43,"D":0x44,"E":0x45,"F":0x46,"G":0x47,
    "H":0x48,"I":0x49,"J":0x4A,"K":0x4B,"L":0x4C,"M":0x4D,"N":0x4E,
    "O":0x4F,"P":0x50,"Q":0x51,"R":0x52,"S":0x53,"T":0x54,"U":0x55,
    "V":0x56,"W":0x57,"X":0x58,"Y":0x59,"Z":0x5A,
    # 넘패드
    "Num Lock":0x90,
    "Num 0":0x60,"Num 1":0x61,"Num 2":0x62,"Num 3":0x63,"Num 4":0x64,
    "Num 5":0x65,"Num 6":0x66,"Num 7":0x67,"Num 8":0x68,"Num 9":0x69,
    "Num *":0x6A,"Num +":0x6B,"Num -":0x6D,"Num .":0x6E,"Num /":0x6F,
    "Num Enter":0x0D,
    # OEM / 특수문자
    "Slash / ?":0xBF,"Minus - _":0xBD,"Period . >":0xBE,
    "Backtick ` ~":0xC0,"Equal = +":0xBB,
    "Left Bracket [ {":0xDB,"Right Bracket ] }":0xDD,
    "Backslash \\ |":0xDC,"Semicolon ; :":0xBA,
    "Apostrophe ' \"":0xDE,"Comma , <":0xBC,
}

def _build_pynput_map():
    if not _HAS_PYNPUT:
        return {}
    from pynput.keyboard import Key, KeyCode
    m = {}
    _fk = {"F1":Key.f1,"F2":Key.f2,"F3":Key.f3,"F4":Key.f4,
           "F5":Key.f5,"F6":Key.f6,"F7":Key.f7,"F8":Key.f8,
           "F9":Key.f9,"F10":Key.f10,"F11":Key.f11,"F12":Key.f12}
    for k,v in _fk.items():
        m[k] = v
    m["Escape"]       = Key.esc
    m["Print Screen"] = Key.print_screen
    m["Scroll Lock"]  = Key.scroll_lock
    m["Pause"]        = Key.pause
    m["Insert"]       = Key.insert
    m["Delete"]       = Key.delete
    m["Home"]         = Key.home
    m["End"]          = Key.end
    m["Page Up"]      = Key.page_up
    m["Page Down"]    = Key.page_down
    m["Arrow Up"]     = Key.up
    m["Arrow Down"]   = Key.down
    m["Arrow Left"]   = Key.left
    m["Arrow Right"]  = Key.right
    m["Num Lock"]     = Key.num_lock
    m["Backspace"]    = Key.backspace
    m["Caps Lock"]    = Key.caps_lock
    m["Tab"]          = Key.tab
    m["Space"]        = Key.space
    m["Ctrl"]         = Key.ctrl
    m["Alt"]          = Key.alt
    m["Shift"]        = Key.shift
    m["Enter"]        = Key.enter
    m["Num Enter"]    = Key.enter
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        m[ch] = KeyCode.from_char(ch.lower())
    return m

_PYNPUT_MAP = _build_pynput_map() if _HAS_PYNPUT else {}
_PYNPUT_KEY_MAP = _PYNPUT_MAP

def _key_matches(k, target_name: str) -> bool:
    if not _HAS_PYNPUT:
        return False
    from pynput.keyboard import Key, KeyCode
    expected = _PYNPUT_MAP.get(target_name)
    if expected is None:
        return False
    if isinstance(expected, Key):
        return k == expected
    if isinstance(expected, KeyCode):
        if isinstance(k, KeyCode):
            if k == expected:
                return True
            if hasattr(k, "vk") and hasattr(expected, "vk") and k.vk and expected.vk:
                return k.vk == expected.vk
    return False

class HotkeySignalEmitter(QObject):
    start_pressed = Signal()
    stop_pressed  = Signal()


# ══════════════════════════════════════════════════
#  네비게이션 리스트 (화살표·Enter·첫글자 점프)
# ══════════════════════════════════════════════════
class _NavList(QListWidget):
    """리스트 위젯 - 키 이벤트를 부모 _NavMenu로 포워딩"""
    itemSelected = Signal(str)

    def keyPressEvent(self, event):
        # 직접 참조가 있으면 빠른 경로 사용 (QWidgetAction 컨테이너 우회)
        if hasattr(self, '_nav_menu') and self._nav_menu is not None:
            self._nav_menu.navigate(event)
            return
        # 폴백: 부모 체인 탐색
        parent = self.parent()
        while parent and not isinstance(parent, _NavMenu):
            parent = parent.parent()
        if parent:
            parent.navigate(event)
        else:
            super().keyPressEvent(event)


# ══════════════════════════════════════════════════
#  네비게이션 메뉴 (QMenu 서브클래스 - 키 이벤트 처리)
# ══════════════════════════════════════════════════
class _NavMenu(QMenu):
    """QMenu 서브클래스 - 참조파일(DirectionSelectMenu) 방식의 키보드 네비게이션."""

    # Qt키 → 표시명 매핑 (참조파일 KEY_MAP과 동일)
    KEY_MAP = {
        Qt.Key_F1: ["F1"],   Qt.Key_F2: ["F2"],   Qt.Key_F3: ["F3"],   Qt.Key_F4: ["F4"],
        Qt.Key_F5: ["F5"],   Qt.Key_F6: ["F6"],   Qt.Key_F7: ["F7"],   Qt.Key_F8: ["F8"],
        Qt.Key_F9: ["F9"],   Qt.Key_F10: ["F10"], Qt.Key_F11: ["F11"], Qt.Key_F12: ["F12"],
        Qt.Key_Escape:    ["Escape"],
        Qt.Key_Print:     ["Print Screen"], Qt.Key_SysReq: ["Print Screen"],
        Qt.Key_ScrollLock:["Scroll Lock"],
        Qt.Key_Pause:     ["Pause"],
        Qt.Key_Insert:    ["Insert"],   Qt.Key_Delete: ["Delete"],
        Qt.Key_Home:      ["Home"],     Qt.Key_End:    ["End"],
        Qt.Key_PageUp:    ["Page Up"],  Qt.Key_PageDown: ["Page Down"],
        Qt.Key_Up:        ["Arrow Up"], Qt.Key_Down:  ["Arrow Down"],
        Qt.Key_Left:      ["Arrow Left"],Qt.Key_Right: ["Arrow Right"],
        Qt.Key_NumLock:   ["Num Lock"],
        Qt.Key_Slash:     ["Slash / ?", "Num /"],
        Qt.Key_Asterisk:  ["Num *"],
        Qt.Key_Minus:     ["Minus - _", "Num -"],
        Qt.Key_Plus:      ["Num +"],
        Qt.Key_Period:    ["Period . >", "Num ."],
        Qt.Key_Return:    ["Enter"],
        Qt.Key_Enter:     ["Num Enter"],
        Qt.Key_0: ["0", "Num 0"], Qt.Key_1: ["1", "Num 1"], Qt.Key_2: ["2", "Num 2"],
        Qt.Key_3: ["3", "Num 3"], Qt.Key_4: ["4", "Num 4"], Qt.Key_5: ["5", "Num 5"],
        Qt.Key_6: ["6", "Num 6"], Qt.Key_7: ["7", "Num 7"], Qt.Key_8: ["8", "Num 8"],
        Qt.Key_9: ["9", "Num 9"],
        Qt.Key_QuoteLeft: ["Backtick ` ~"],
        Qt.Key_Equal:     ["Equal = +"],
        Qt.Key_Backspace: ["Backspace"],
        Qt.Key_Control:   ["Ctrl"], Qt.Key_Alt: ["Alt"], Qt.Key_Shift: ["Shift"],
        Qt.Key_A: ["A"], Qt.Key_B: ["B"], Qt.Key_C: ["C"], Qt.Key_D: ["D"],
        Qt.Key_E: ["E"], Qt.Key_F: ["F"], Qt.Key_G: ["G"], Qt.Key_H: ["H"],
        Qt.Key_I: ["I"], Qt.Key_J: ["J"], Qt.Key_K: ["K"], Qt.Key_L: ["L"],
        Qt.Key_M: ["M"], Qt.Key_N: ["N"], Qt.Key_O: ["O"], Qt.Key_P: ["P"],
        Qt.Key_Q: ["Q"], Qt.Key_R: ["R"], Qt.Key_S: ["S"], Qt.Key_T: ["T"],
        Qt.Key_U: ["U"], Qt.Key_V: ["V"], Qt.Key_W: ["W"], Qt.Key_X: ["X"],
        Qt.Key_Y: ["Y"], Qt.Key_Z: ["Z"],
        Qt.Key_Tab:          ["Tab"],
        Qt.Key_CapsLock:     ["Caps Lock"],
        Qt.Key_Space:        ["Space"],
        Qt.Key_Menu:         ["Menu"],
        Qt.Key_BracketLeft:  ["Left Bracket [ {"],
        Qt.Key_BracketRight: ["Right Bracket ] }"],
        Qt.Key_Backslash:    ["Backslash \\ |"],
        Qt.Key_Semicolon:    ["Semicolon ; :"],
        Qt.Key_Apostrophe:   ["Apostrophe ' \""],
        Qt.Key_Comma:        ["Comma , <"],
    }

    def __init__(self, list_widget: _NavList, parent=None):
        super().__init__(parent)
        self._list          = list_widget
        self._item_to_row: dict = {}
        self._last_key      = None
        self._last_was_kp   = False
        self._cycle_index   = 0

    def showEvent(self, event):
        super().showEvent(event)
        # 표시명 → 행 번호 룩업 테이블 구성
        self._item_to_row = {
            self._list.item(i).text(): i
            for i in range(self._list.count())
        }
        self._last_key    = None
        self._last_was_kp = False
        self._cycle_index = 0
        # 현재 선택 항목으로 스크롤
        btn = self.parent()
        if btn and hasattr(btn, '_current'):
            current = btn._current
            if current in self._item_to_row:
                row = self._item_to_row[current]
                self._list.setCurrentRow(row)
                self._list.scrollToItem(
                    self._list.item(row), QListWidget.PositionAtCenter)

    def navigate(self, event):
        """키 이벤트를 받아 해당 항목으로 이동하고 즉시 선택 적용."""
        key   = event.key()
        is_kp = bool(event.modifiers() & Qt.KeyboardModifier.KeypadModifier)

        if key not in self.KEY_MAP:
            return

        candidates = self.KEY_MAP[key]
        # 넘패드 키는 "Num "으로 시작하는 항목, 일반 키는 그 외 항목으로 필터링
        if is_kp:
            filtered = [n for n in candidates if n.startswith("Num ")] or candidates
        else:
            filtered = [n for n in candidates if not n.startswith("Num ")] or candidates

        # 같은 키를 연속으로 누르면 후보 목록 사이클
        if key == self._last_key and is_kp == self._last_was_kp:
            self._cycle_index = (self._cycle_index + 1) % len(filtered)
        else:
            self._last_key    = key
            self._last_was_kp = is_kp
            self._cycle_index = 0

        item_name = filtered[self._cycle_index]
        if item_name not in self._item_to_row:
            return

        row = self._item_to_row[item_name]
        self._list.setCurrentRow(row)
        self._list.scrollToItem(self._list.item(row), QListWidget.PositionAtCenter)

        # 즉시 선택 적용 (버튼 텍스트 갱신 + 시그널 발행)
        btn = self.parent()
        if btn and hasattr(btn, '_current'):
            btn._current = item_name
            btn._update_text(item_name)
            btn.selectionChanged.emit(item_name)

    def keyPressEvent(self, event):
        self.navigate(event)


# ══════════════════════════════════════════════════
#  핫키 드롭다운 버튼 (DirectionSelectButton 다크테마)
# ══════════════════════════════════════════════════
class HotkeyDropdown(QPushButton):
    selectionChanged = Signal(str)

    def __init__(self, options: list, parent=None):
        super().__init__(parent)
        self._options = options
        self._current = options[0] if options else ""
        self._setup()

    def _setup(self):
        self._arrow = QLabel("▼", self)
        self._arrow.setStyleSheet(
            f"color:{TEXT}; background:transparent; border:none; font-size:10px;")
        self._arrow.setFixedSize(14, 28)
        self._arrow.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._list = _NavList()
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background:{DARK_BG}; color:{TEXT};
                font-size:12px; border:none; outline:none;
            }}
            QListWidget::item {{
                padding:2px 6px; height:26px; min-height:26px; max-height:26px;
            }}
            QListWidget::item:hover    {{ background:{DARK_PANEL}; }}
            QListWidget::item:selected {{ background:{ACCENT}; color:#fff; }}
            QScrollBar:vertical {{
                background:{DARK_BG}; width:6px; border:none;
            }}
            QScrollBar::handle:vertical {{
                background:{DARK_BORDER}; min-height:20px; border-radius:3px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0px; }}
        """)
        for opt in self._options:
            item = QListWidgetItem(opt)
            item.setSizeHint(QSize(100, 26))
            self._list.addItem(item)
        self._list.setFixedHeight(26 * min(10, len(self._options)))
        self._list.itemClicked.connect(self._on_selected)
        self._list.itemSelected.connect(self._on_selected_text)

        self._menu = _NavMenu(self._list, self)
        self._list._nav_menu = self._menu   # 직접 참조 — keyPressEvent 빠른 경로용
        self._menu.setStyleSheet(f"""
            QMenu {{
                background:{DARK_BG}; border:1px solid {ACCENT}; padding:0px;
            }}
        """)
        act = QWidgetAction(self._menu)
        act.setDefaultWidget(self._list)
        self._menu.addAction(act)
        self.setMenu(self._menu)

        self.setStyleSheet(f"""
            QPushButton {{
                background:{DARK_PANEL}; color:{TEXT};
                font-size:12px; font-weight:bold;
                border:1px solid {ACCENT}; text-align:left;
            }}
            QPushButton:hover    {{ background:{DARK_BG}; border-color:{ACCENT_H}; }}
            QPushButton:disabled {{ background:{DARK_BORDER}; color:{TEXT_DIM};
                                   border-color:{DARK_BORDER}; }}
            QPushButton::menu-indicator {{ image:none; width:0px; }}
        """)
        self._update_text(self._current)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_arrow'):
            self._arrow.move(self.width() - self._arrow.width() - 4, 0)
        if hasattr(self, '_menu') and hasattr(self, '_list'):
            self._menu.setFixedWidth(self.width())
            self._list.setFixedWidth(self.width() - 2)
            for i in range(self._list.count()):
                item = self._list.item(i)
                if item:
                    item.setSizeHint(QSize(self.width() - 2, 26))

    def _update_text(self, text: str):
        self.setText(f"  {text.replace('&', '&&')}")

    def _on_selected(self, item: QListWidgetItem):
        self._current = item.text()
        self._update_text(self._current)
        self.selectionChanged.emit(self._current)
        self._menu.close()

    def _on_selected_text(self, text: str):
        self._current = text
        self._update_text(self._current)
        self.selectionChanged.emit(self._current)
        self._menu.close()

    def currentText(self) -> str:
        return self._current

    def setCurrentText(self, text: str):
        self._current = text
        self._update_text(text)
        for i in range(self._list.count()):
            if self._list.item(i).text() == text:
                self._list.setCurrentRow(i)
                break

    def install_portal_align(self):
        """'X 포탈 | 지역명' 형식 목록에 두-열 정렬 델리게이트를 설치한다."""
        self._portal_align = True
        self._list.setItemDelegate(_PortalItemDelegate(self._list))
        self.update()

    def paintEvent(self, event):
        if not getattr(self, '_portal_align', False):
            super().paintEvent(event)
            return

        # 버튼 배경·테두리만 그리기 (텍스트 제외)
        sp = QStylePainter(self)
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        opt.text = ""
        sp.drawControl(QStyle.ControlElement.CE_PushButton, opt)
        sp.end()

        # 두 열 텍스트 그리기
        painter = QPainter(self)
        painter.setFont(self.font())
        fg = QColor(TEXT_DIM) if not self.isEnabled() else QColor(TEXT)
        painter.setPen(fg)

        text  = self._current
        parts = text.split(_PortalItemDelegate._SEP, 1)
        left  = parts[0]
        right = parts[1] if len(parts) > 1 else ""

        r   = self.rect()
        PAD = _PortalItemDelegate._PAD_L + 2
        C1  = _PortalItemDelegate._COL1_W
        SW  = _PortalItemDelegate._SEP_W
        right_margin = self._arrow.width() + 8

        x0 = r.left() + PAD
        painter.drawText(QRect(x0,          r.top(), C1, r.height()),
                         Qt.AlignVCenter | Qt.AlignLeft,    left)
        painter.drawText(QRect(x0 + C1,     r.top(), SW, r.height()),
                         Qt.AlignVCenter | Qt.AlignHCenter, "|")
        painter.drawText(QRect(x0 + C1 + SW, r.top(),
                               r.width() - PAD - C1 - SW - right_margin, r.height()),
                         Qt.AlignVCenter | Qt.AlignLeft,    right)
        painter.end()


# ══════════════════════════════════════════════════
#  포탈 드롭다운 두-열 정렬 델리게이트
# ══════════════════════════════════════════════════
class _PortalItemDelegate(QStyledItemDelegate):
    """'X 포탈 | 지역명' 텍스트를 두 열로 나눠 고정 위치에 그린다."""
    _SEP    = " | "
    _COL1_W = 58   # "X 포탈" 열 너비 (px)
    _SEP_W  = 16   # "|" 구분자 너비 (px)
    _PAD_L  = 6    # 왼쪽 여백 (px)

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.text = ""   # 배경만 그리도록 — 텍스트는 paint()에서 직접

    def sizeHint(self, option, index):
        # initStyleOption에서 text=""로 비우면 기본 sizeHint가 높이를 잘못 계산하므로
        # 아이템에 저장된 SizeHintRole을 우선 사용하고, 없으면 26px 고정
        sh = index.data(Qt.SizeHintRole)
        return sh if sh is not None else QSize(option.rect.width(), 26)

    def paint(self, painter, option, index):
        # super().paint()가 initStyleOption()을 내부 호출 → text="" → 배경(hover/selected)만 그려짐
        super().paint(painter, option, index)

        text  = index.data(Qt.DisplayRole) or ""
        parts = text.split(self._SEP, 1)
        left  = parts[0]
        right = parts[1] if len(parts) > 1 else ""

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        fg = QColor("#ffffff") if selected else QColor(TEXT)

        painter.save()
        painter.setPen(fg)
        r = option.rect

        x0 = r.left() + self._PAD_L
        r_left  = QRect(x0,                              r.top(), self._COL1_W, r.height())
        r_sep   = QRect(x0 + self._COL1_W,               r.top(), self._SEP_W,  r.height())
        r_right = QRect(x0 + self._COL1_W + self._SEP_W, r.top(),
                        r.width() - self._PAD_L - self._COL1_W - self._SEP_W, r.height())

        painter.drawText(r_left,  Qt.AlignVCenter | Qt.AlignLeft,    left)
        painter.drawText(r_sep,   Qt.AlignVCenter | Qt.AlignHCenter, "|")
        painter.drawText(r_right, Qt.AlignVCenter | Qt.AlignLeft,    right)
        painter.restore()


# ══════════════════════════════════════════════════
#  커스텀 좌표 서브패널 (최대 3개 경유지)
# ══════════════════════════════════════════════════
class _CustomCoordsPanel(QWidget):
    """커스텀 좌표 3개까지 입력받는 서브패널. cfg_key 에 [[x,y]×3] 저장."""

    def __init__(self, cfg_key: str, parent=None):
        super().__init__(parent)
        self._cfg_key = cfg_key
        self._spins: "list[tuple[QSpinBox, QSpinBox]]" = []
        self._build_ui()

    def _build_ui(self):
        cfg   = load_config()
        saved = cfg.get(self._cfg_key, [])
        while len(saved) < 3:
            saved.append([0, 0])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 2, 0, 4)
        outer.setSpacing(4)

        _spn_ss = (
            f"QSpinBox {{"
            f"  background:{DARK_BG}; color:{TEXT};"
            f"  border:1px solid {DARK_BORDER}; border-radius:4px;"
            f"  padding:2px 4px; font-size:12px;"
            f"}}"
            f"QSpinBox::up-button, QSpinBox::down-button {{ width:0px; }}"
        )

        for i in range(3):
            row = QHBoxLayout()
            row.setSpacing(6)

            lbl = QLabel(f"경유지 {i + 1} :")
            lbl.setFixedWidth(62)
            row.addWidget(lbl)

            lbl_x = QLabel("X")
            lbl_x.setFixedWidth(12)
            row.addWidget(lbl_x)

            spn_x = QSpinBox()
            spn_x.setRange(0, 9999)
            spn_x.setValue(saved[i][0])
            spn_x.setFixedWidth(72)
            spn_x.setStyleSheet(_spn_ss)
            row.addWidget(spn_x)

            lbl_y = QLabel("Y")
            lbl_y.setFixedWidth(12)
            row.addWidget(lbl_y)

            spn_y = QSpinBox()
            spn_y.setRange(0, 9999)
            spn_y.setValue(saved[i][1])
            spn_y.setFixedWidth(72)
            spn_y.setStyleSheet(_spn_ss)
            row.addWidget(spn_y)

            row.addStretch()
            outer.addLayout(row)
            self._spins.append((spn_x, spn_y))

        for spn_x, spn_y in self._spins:
            spn_x.valueChanged.connect(self._save)
            spn_y.valueChanged.connect(self._save)

    def _save(self):
        coords = [[sx.value(), sy.value()] for sx, sy in self._spins]
        cfg = load_config()
        cfg[self._cfg_key] = coords
        save_config(cfg)


# ══════════════════════════════════════════════════
#  핫키 설정 다이얼로그
# ══════════════════════════════════════════════════
class HotkeyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("시작키/중지키 설정")
        self.setFixedSize(380, 280)
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background:{DARK_BG}; color:{TEXT};
                               font-family:'Segoe UI'; font-size:13px; }}
            QLabel  {{ background:transparent; }}
            QPushButton {{
                background:{ACCENT}; color:#fff; border:none;
                border-radius:6px; padding:6px 18px; font-weight:bold;
            }}
            QPushButton:hover    {{ background:{ACCENT_H}; }}
            QPushButton:disabled {{ background:{DARK_BORDER}; color:{TEXT_DIM}; }}
        """)
        cfg = load_config()
        self._build_ui(cfg)

    def _mod_toggle(self, cfg_key: bool) -> "ToggleSwitch":
        t = ToggleSwitch(cfg_key)
        t.setFixedSize(34, 18)
        return t

    def _build_ui(self, cfg: dict):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(6)

        for role, key_cfg, ctrl_cfg, alt_cfg, shift_cfg, attr_suffix in [
            ("시작 키", "hotkey_start_key", "hotkey_start_ctrl",
             "hotkey_start_alt", "hotkey_start_shift", "start"),
            ("중지 키", "hotkey_stop_key",  "hotkey_stop_ctrl",
             "hotkey_stop_alt",  "hotkey_stop_shift",  "stop"),
        ]:
            # Row 1: label + dropdown
            key_row = QHBoxLayout(); key_row.setSpacing(8)
            lbl = QLabel(role); lbl.setFixedWidth(52)
            key_row.addWidget(lbl)
            dd = HotkeyDropdown(_ALL_KEYS)
            dd.setFixedSize(200, 30)
            dd.setCurrentText(cfg.get(key_cfg, "F2" if attr_suffix == "start" else "F4"))
            setattr(self, f"_dd_{attr_suffix}", dd)
            key_row.addWidget(dd)
            key_row.addStretch()
            root.addLayout(key_row)

            # Row 2: modifier toggles
            mod_row = QHBoxLayout(); mod_row.setSpacing(6)
            mod_row.addSpacing(60)
            for mod_label, cfg_key in [("Ctrl", ctrl_cfg),
                                        ("Alt",  alt_cfg),
                                        ("Shift", shift_cfg)]:
                tog = self._mod_toggle(cfg.get(cfg_key, False))
                setattr(self, f"_tog_{attr_suffix}_{mod_label.lower()}", tog)
                mod_row.addWidget(tog)
                lbl_m = QLabel(mod_label)
                lbl_m.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
                mod_row.addWidget(lbl_m)
                mod_row.addSpacing(6)
            mod_row.addStretch()
            root.addLayout(mod_row)
            root.addSpacing(10)

        # Confirm / Cancel
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{DARK_BORDER};")
        root.addWidget(sep)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("Confirm")
        btn_box.button(QDialogButtonBox.Cancel).setText("Cancel")
        btn_box.accepted.connect(self._on_confirm)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    def _on_confirm(self):
        cfg = load_config()
        cfg["hotkey_start_key"]   = self._dd_start.currentText()
        cfg["hotkey_start_ctrl"]  = self._tog_start_ctrl.isChecked()
        cfg["hotkey_start_alt"]   = self._tog_start_alt.isChecked()
        cfg["hotkey_start_shift"] = self._tog_start_shift.isChecked()
        cfg["hotkey_stop_key"]    = self._dd_stop.currentText()
        cfg["hotkey_stop_ctrl"]   = self._tog_stop_ctrl.isChecked()
        cfg["hotkey_stop_alt"]    = self._tog_stop_alt.isChecked()
        cfg["hotkey_stop_shift"]  = self._tog_stop_shift.isChecked()
        save_config(cfg)
        self.accept()


# ══════════════════════════════════════════════════
#  토글 스위치 위젯 (iOS 스타일)
# ══════════════════════════════════════════════════
class ToggleSwitch(QWidget):
    """iOS 스타일 슬라이드 토글. Signal: toggled(bool)"""
    toggled = Signal(bool)
    _W, _H = 34, 18

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._pos     = 1.0 if checked else 0.0
        self._target  = self._pos
        self._hover   = False
        self._anim    = QTimer(self)
        self._anim.setInterval(16)
        self._anim.timeout.connect(self._step)
        self.setFixedSize(self._W, self._H)
        self.setAttribute(Qt.WA_Hover, True)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, val: bool):
        if val != self._checked:
            self._checked = val
            self._target  = 1.0 if val else 0.0
            self._anim.start()

    def _step(self):
        diff = self._target - self._pos
        if abs(diff) < 0.02:
            self._pos = self._target
            self._anim.stop()
        else:
            self._pos += diff * 0.25
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._checked = not self._checked
            self._target  = 1.0 if self._checked else 0.0
            self._anim.start()
            self.toggled.emit(self._checked)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self._W, self._H
        r    = H / 2
        t    = self._pos
        dim  = not self.isEnabled()

        bg_off = QColor(DARK_BORDER)
        bg_on  = QColor(ACCENT)
        bg = QColor(
            int(bg_off.red()   + t * (bg_on.red()   - bg_off.red())),
            int(bg_off.green() + t * (bg_on.green() - bg_off.green())),
            int(bg_off.blue()  + t * (bg_on.blue()  - bg_off.blue())),
        )
        if self._hover and self.isEnabled():
            bg = bg.lighter(120)
        if dim:
            bg.setAlpha(100)
        p.setBrush(bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, W, H, r, r)

        kr      = r - 2
        knob_cx = r + t * (W - H)
        knob_cy = H / 2
        knob_c  = QColor(255, 255, 255, 100 if dim else 255)
        p.setBrush(knob_c)
        p.drawEllipse(QPointF(knob_cx, knob_cy), kr, kr)


# ══════════════════════════════════════════════════
#  OCR 영역 선택 오버레이 (라이브 드래그 → 물리좌표 QRect 반환)
# ══════════════════════════════════════════════════
class OcrRegionSelector(QWidget):
    """모든 모니터에 걸쳐 드래그 → 물리픽셀 QRect 반환."""
    region_selected = Signal(object)   # QRect (물리픽셀)
    cancelled       = Signal()

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self._origin = QPoint()
        self._rubber = QRubberBand(QRubberBand.Rectangle, self)

    def start(self):
        combined = QRect()
        for screen in QApplication.screens():
            combined = combined.united(screen.geometry())
        self.setGeometry(combined)
        self.show()
        self.raise_()
        self.activateWindow()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._origin = e.position().toPoint()
            self._rubber.setGeometry(QRect(self._origin, QSize()))
            self._rubber.show()

    def mouseMoveEvent(self, e):
        if not self._origin.isNull():
            self._rubber.setGeometry(
                QRect(self._origin, e.position().toPoint()).normalized()
            )

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            rect = QRect(self._origin, e.position().toPoint()).normalized()
            self._rubber.hide()
            self.hide()
            self._origin = QPoint()
            if rect.width() > 5 and rect.height() > 5:
                screen = QApplication.screenAt(rect.center())
                if screen is None:
                    screen = QApplication.primaryScreen()
                dpr = screen.devicePixelRatio()
                phys = QRect(
                    int(rect.x() * dpr), int(rect.y() * dpr),
                    int(rect.width() * dpr), int(rect.height() * dpr),
                )
                self.region_selected.emit(phys)
            else:
                self.cancelled.emit()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._rubber.hide()
            self._origin = QPoint()
            self.hide()
            self.cancelled.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 80))
        p.setPen(QColor("#cdd6f4"))
        p.setFont(QFont("Segoe UI", 14))
        p.drawText(self.rect(), Qt.AlignCenter, "드래그하여 OCR 영역 선택\nESC: 취소")


# ══════════════════════════════════════════════════
#  OCR 프리징 영역 선택 오버레이 (스냅샷 방식)
# ══════════════════════════════════════════════════
class OcrFrozenSelector(QWidget):
    """전체 모니터 스크린샷을 프리징하여 OCR 영역 드래그 선택 → 물리픽셀 QRect 반환."""
    region_selected = Signal(object)   # QRect (물리픽셀)
    cancelled       = Signal()

    def __init__(self, pixmap: "QPixmap", virt_rect: "QRect"):
        super().__init__(None)
        self._pixmap    = pixmap
        self._virt_rect = virt_rect
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setCursor(Qt.CrossCursor)
        self._origin = QPoint()
        self._rubber = QRubberBand(QRubberBand.Rectangle, self)

    def start(self):
        self.setGeometry(self._virt_rect)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, _):
        from PySide6.QtGui import QPainter as _P, QColor as _C, QFont as _F
        p = _P(self)
        p.drawPixmap(self.rect(), self._pixmap)
        p.fillRect(self.rect(), _C(0, 0, 0, 80))
        p.setPen(_C(255, 255, 255, 220))
        p.setFont(_F("Segoe UI", 14))
        p.drawText(self.rect(), Qt.AlignCenter,
                   "드래그하여 OCR 영역 선택\nESC: 취소")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._origin = e.position().toPoint()
            self._rubber.setGeometry(QRect(self._origin, QSize()))
            self._rubber.show()

    def mouseMoveEvent(self, e):
        if not self._origin.isNull():
            self._rubber.setGeometry(
                QRect(self._origin, e.position().toPoint()).normalized()
            )

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            rect = QRect(self._origin, e.position().toPoint()).normalized()
            self._rubber.hide()
            self.hide()
            self.close()
            self._origin = QPoint()
            if rect.width() > 5 and rect.height() > 5:
                screen = QApplication.screenAt(rect.center())
                if screen is None:
                    screen = QApplication.primaryScreen()
                dpr = screen.devicePixelRatio()
                phys = QRect(
                    int(rect.x() * dpr), int(rect.y() * dpr),
                    int(rect.width() * dpr), int(rect.height() * dpr),
                )
                self.region_selected.emit(phys)
            else:
                self.cancelled.emit()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._rubber.hide()
            self._origin = QPoint()
            self.hide()
            self.close()
            self.cancelled.emit()


# ══════════════════════════════════════════════════
#  스냅샷 영역 선택 오버레이
# ══════════════════════════════════════════════════
class SnapshotRegionSelector(QWidget):
    """화면을 정지 이미지로 보여주면서 드래그로 영역 선택 → 크롭된 QPixmap 반환."""
    region_selected = Signal(object)   # cropped QPixmap
    cancelled       = Signal()

    def __init__(self, pixmap: "QPixmap", screen_geometry: "QRect"):
        super().__init__(None)
        self._pixmap    = pixmap
        self._screen_geo = screen_geometry
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setCursor(Qt.CrossCursor)
        self._origin = QPoint()
        self._rubber = QRubberBand(QRubberBand.Rectangle, self)

    def start(self):
        self.setGeometry(self._screen_geo)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, _):
        from PySide6.QtGui import QPainter, QColor, QFont as _QFont
        p = QPainter(self)
        p.drawPixmap(self.rect(), self._pixmap)
        p.fillRect(self.rect(), QColor(0, 0, 0, 80))
        p.setPen(QColor(255, 255, 255, 220))
        p.setFont(_QFont("Segoe UI", 14))
        p.drawText(self.rect(), Qt.AlignCenter,
                   "드래그하여 캡처 영역 선택\nESC: 취소")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._origin = e.position().toPoint()
            self._rubber.setGeometry(QRect(self._origin, QSize()))
            self._rubber.show()

    def mouseMoveEvent(self, e):
        if not self._origin.isNull():
            self._rubber.setGeometry(
                QRect(self._origin, e.position().toPoint()).normalized()
            )

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            rect = QRect(self._origin, e.position().toPoint()).normalized()
            self._rubber.hide()
            self.hide()
            self.close()
            self._origin = QPoint()
            if rect.width() > 5 and rect.height() > 5:
                self.region_selected.emit(self._pixmap.copy(rect))
            else:
                self.cancelled.emit()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._rubber.hide()
            self._origin = QPoint()
            self.hide()
            self.close()
            self.cancelled.emit()


# ══════════════════════════════════════════════════
#  관리자 커서 오버레이
# ══════════════════════════════════════════════════
class AdminCursorOverlay(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._build()

    def _build(self):
        _FONT = QFont("Consolas", 10)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        def _lbl(text=""):
            l = QLabel(text)
            l.setFont(_FONT)
            l.setStyleSheet("color:#ffffff; background:transparent; border:none;")
            return l

        # Row 1: "X:1234  Y:5678" + swatch
        row1 = QHBoxLayout(); row1.setSpacing(6); row1.setContentsMargins(0,0,0,0)
        self.lbl_xy = _lbl("X:   —   Y:   —")
        self.lbl_sw = QLabel()
        self.lbl_sw.setFixedSize(16, 16)
        self.lbl_sw.setStyleSheet("background:#000000; border:1px solid #888888; border-radius:3px;")
        row1.addWidget(self.lbl_xy)
        row1.addWidget(self.lbl_sw)
        row1.addStretch()

        # Row 2: "R: 255  G: 128  B:  64"
        self.lbl_rgb = _lbl("R:  —   G:  —   B:  —")

        # Row 3: Capture key + exit hint
        row3 = QHBoxLayout(); row3.setSpacing(12); row3.setContentsMargins(0, 0, 0, 0)
        self.lbl_cap = _lbl("Capture: —")
        self.lbl_cap.setStyleSheet("color:#aaaaaa; background:transparent; border:none;")
        lbl_exit = _lbl("exit: `~")
        lbl_exit.setStyleSheet("color:#ffffff; background:transparent; border:none;")
        row3.addWidget(self.lbl_cap)
        row3.addWidget(lbl_exit)
        row3.addStretch()

        lay.addLayout(row1)
        lay.addWidget(self.lbl_rgb)
        lay.addLayout(row3)

        self.adjustSize()

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(0, 0, 0, 220))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 7, 7)

    def refresh(self, coord, rgb, capture_key: str, frozen: bool = False):
        if coord:
            self.lbl_xy.setText(f"X:{coord[0]:4d}  Y:{coord[1]:4d}")
        else:
            self.lbl_xy.setText("X:   —   Y:   —")

        if rgb:
            r, g, b = rgb
            self.lbl_rgb.setText(f"R:{r:3d}  G:{g:3d}  B:{b:3d}")
            self.lbl_sw.setStyleSheet(
                f"background:#{r:02x}{g:02x}{b:02x}; border:1px solid #888888; border-radius:3px;"
            )
        else:
            self.lbl_rgb.setText("R:  —   G:  —   B:  —")
            self.lbl_sw.setStyleSheet("background:#000000; border:1px solid #888888; border-radius:3px;")

        if frozen:
            self.lbl_cap.setText("⏸ FROZEN")
            self.lbl_cap.setStyleSheet("color:#f9e2af; background:transparent; border:none;")
        else:
            self.lbl_cap.setText(f"Capture: [{capture_key}]")
            self.lbl_cap.setStyleSheet("color:#aaaaaa; background:transparent; border:none;")
        self.adjustSize()

    def follow_cursor(self):
        from PySide6.QtCore import QPoint
        pt = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        x, y = pt.x + 18, pt.y + 18
        # 커서가 있는 모니터 기준으로 경계 계산 (서브 모니터 대응)
        cur_screen = QApplication.screenAt(QPoint(pt.x, pt.y))
        if cur_screen is None:
            cur_screen = QApplication.primaryScreen()
        screen = cur_screen.geometry()
        if x + self.width()  > screen.right():  x = pt.x - self.width()  - 4
        if y + self.height() > screen.bottom(): y = pt.y - self.height() - 4
        self.move(x, y)
        self.raise_()


# ══════════════════════════════════════════════════
#  메인 윈도우
# ══════════════════════════════════════════════════
class MainWindow(QMainWindow):
    _admin_capture_signal = Signal(str)   # 백그라운드 스레드 → 메인 스레드 클립보드 복사
    _admin_save_signal    = Signal()      # 이미지 저장 핫키 트리거
    _admin_toggle_signal  = Signal()      # ` ~ 키 → 어드민 모드 토글

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NOX 매크로")
        self.setMinimumSize(670, 892)
        self.resize(670, 961)
        self._thread: QThread | None = None
        self._worker: WatchWorker | None = None
        self._war3_gone_ticks = 0
        self._pending_recovery = False

        self._build_ui()
        self._apply_theme()

        # ── War3 프로세스 모니터 (0.25초 간격) ──
        self._war3_monitor = QTimer(self)
        self._war3_monitor.setInterval(250)
        self._war3_monitor.timeout.connect(self._check_war3_alive)
        self._war3_monitor.start()
        # ── 녹스 맵 자동 다운로드 타이머 (5분 간격) ──
        self._nox_checking = False
        self._nox_signals  = _NoxSignals(self)
        self._nox_signals.log_sig.connect(self._nox_append_log)
        self._nox_signals.update_sig.connect(self._nox_update_last_log)
        self._nox_signals.status_sig.connect(self._nox_set_status)
        self._nox_timer = QTimer(self)
        self._nox_timer.setInterval(5 * 60 * 1000)
        self._nox_timer.timeout.connect(self._nox_check_now)
        if load_config().get("nox_map_enabled", True):
            self._nox_timer.start()
            QTimer.singleShot(1000, self._nox_check_now)
        # ── 핫키 리스너 ──
        self._hotkey_emitter      = HotkeySignalEmitter(self)
        self._hotkey_listener     = None
        self._hotkey_dialog_open  = False
        self._hotkey_emitter.start_pressed.connect(self._start)
        self._hotkey_emitter.stop_pressed.connect(self._stop)
        self._start_hotkey_listener()
        self._overlay = OverlayWindow()
        self._unclip_timer = QTimer(self)
        self._unclip_timer.setInterval(100)
        self._unclip_timer.timeout.connect(
            lambda: ctypes.windll.user32.ClipCursor(None)
        )
        # ── 관리자 전용 실시간 갱신 (10ms) ──
        self._admin_frozen       = False
        self._snapshot_pixmap    = None
        self._admin_save_listener = None
        self._admin_timer = QTimer(self)
        self._admin_timer.setInterval(10)
        self._admin_timer.timeout.connect(self._update_admin_display)
        # ── 관리자 캡처 핫키 ──
        self._admin_capture_listener = None
        self._admin_capture_signal.connect(self._on_admin_captured)
        self._admin_save_signal.connect(self._on_save_hotkey_triggered)
        self._admin_toggle_signal.connect(self._on_admin_hotkey)
        self._admin_toggle_listener = None
        self._start_admin_toggle_listener()
        # ── 관리자 커서 오버레이 ──
        self._admin_overlay = AdminCursorOverlay()
        # ── OCR 모니터 ──
        self._ocr_region: "QRect | None" = None
        self._ocr_timer = QTimer(self)
        self._ocr_timer.timeout.connect(self._run_ocr_monitor)
        self._ocr_frozen_selector = None   # OcrFrozenSelector (on-demand)

    # ── UI 구성 ───────────────────────────────────
    def _build_ui(self):
        _cfg = load_config()
        is_host = (_cfg.get("role", "guest") == "host")

        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        left_widget = QWidget()
        self._main_panel = left_widget
        root = QVBoxLayout(left_widget)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        outer.addWidget(left_widget, stretch=0)

        # ── 헤더 (타이틀 + 상태 + 시작/중지) ────────
        hdr = QHBoxLayout()
        title = QLabel("NOX 매크로")
        title.setStyleSheet(f"color:{ACCENT}; font-size:16px; font-weight:bold;")
        hdr.addWidget(title)
        self.lbl_status = QLabel("대기 중")
        self.lbl_status.setStyleSheet(f"color:{TEXT_DIM}; font-size:12px; padding-left:10px;")
        hdr.addWidget(self.lbl_status)
        hdr.addStretch()
        self.btn_start = QPushButton("▶  시작")
        self.btn_stop  = QPushButton("■  중지")
        self.btn_start.setFixedSize(90, 30)
        self.btn_stop.setFixedSize(80, 30)
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        hdr.addWidget(self.btn_start)
        hdr.addWidget(self.btn_stop)
        root.addLayout(hdr)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet(f"color:{DARK_BORDER};")
        root.addWidget(sep1)

        # ── 탭 위젯 ───────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.tabBar().setUsesScrollButtons(False)

        # 탭 네비게이션 버튼 (왼쪽 코너)
        nav_w = QWidget()
        nav_l = QHBoxLayout(nav_w)
        nav_l.setContentsMargins(2, 2, 2, 2)
        nav_l.setSpacing(2)
        _tab_btn_style = f"""
            QPushButton {{
                background-color:{DARK_PANEL}; color:{TEXT};
                border:1px solid {DARK_BORDER}; border-radius:3px;
                padding:0px; font-size:10px;
            }}
            QPushButton:hover {{ background-color:{DARK_BG}; border-color:{ACCENT}; }}
            QPushButton:pressed {{ background-color:{ACCENT}; color:#fff; }}
            QPushButton:disabled {{ background-color:{DARK_BG}; color:{TEXT_DIM};
                                    border-color:{DARK_BORDER}; }}
        """
        btn_tab_prev = QPushButton("◀")
        btn_tab_next = QPushButton("▶")
        btn_tab_prev.setFixedSize(22, 22)
        btn_tab_next.setFixedSize(22, 22)
        btn_tab_prev.setStyleSheet(_tab_btn_style)
        btn_tab_next.setStyleSheet(_tab_btn_style)
        self._btn_tab_prev = btn_tab_prev
        self._btn_tab_next = btn_tab_next

        btn_tab_prev.clicked.connect(
            lambda: self.tabs.setCurrentIndex(self.tabs.currentIndex() - 1))
        btn_tab_next.clicked.connect(
            lambda: self.tabs.setCurrentIndex(self.tabs.currentIndex() + 1))
        self.tabs.currentChanged.connect(self._update_tab_nav_buttons)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        nav_l.addWidget(btn_tab_prev)
        nav_l.addWidget(btn_tab_next)
        self.tabs.setCornerWidget(nav_w, Qt.TopLeftCorner)

        root.addWidget(self.tabs)

        self._build_tab1()
        self._build_tab2()
        self._build_tab3()
        self._build_tab4()
        self._build_tab567()
        self._update_tab_nav_buttons(0)   # 초기 상태: ◀ 비활성

        # 초기 비활성 UI 상태 적용
        self._on_role_changed(is_host)

        # ── 오른쪽 로그 패널 (기본 숨김) ─────────────
        self.log_panel = QWidget()
        self.log_panel.setMinimumWidth(540)
        self.log_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        log_layout = QVBoxLayout(self.log_panel)
        log_layout.setContentsMargins(8, 14, 16, 14)
        log_layout.setSpacing(6)

        log_hdr = QHBoxLayout()
        log_hdr.addWidget(QLabel("로그"))
        log_hdr.addStretch()
        btn_clear = QPushButton("지우기"); btn_clear.setFixedWidth(72)
        btn_clear.clicked.connect(lambda: self.log_edit.clear())
        log_hdr.addWidget(btn_clear)
        log_layout.addLayout(log_hdr)

        sep_log = QFrame(); sep_log.setFrameShape(QFrame.HLine)
        sep_log.setStyleSheet(f"color:{DARK_BORDER};")
        log_layout.addWidget(sep_log)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_edit)

        self.log_panel.hide()
        outer.addWidget(self.log_panel, stretch=1)

        # ── 오른쪽 Logic 설명 패널 (기본 숨김) ───────────
        self.logic_panel = QWidget()
        self.logic_panel.setMinimumWidth(540)
        self.logic_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        logic_layout = QVBoxLayout(self.logic_panel)
        logic_layout.setContentsMargins(8, 14, 16, 14)
        logic_layout.setSpacing(6)

        logic_hdr = QHBoxLayout()
        _logic_title = QLabel("Logic 설명")
        _logic_title.setStyleSheet(f"color:{ACCENT}; font-weight:bold; font-size:13px;")
        logic_hdr.addWidget(_logic_title)
        logic_hdr.addStretch()
        logic_layout.addLayout(logic_hdr)

        sep_logic = QFrame(); sep_logic.setFrameShape(QFrame.HLine)
        sep_logic.setStyleSheet(f"color:{DARK_BORDER};")
        logic_layout.addWidget(sep_logic)

        self._logic_desc_label = QLabel()
        self._logic_desc_label.setTextFormat(Qt.RichText)
        self._logic_desc_label.setWordWrap(True)
        self._logic_desc_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._logic_desc_label.setStyleSheet(
            f"background:{DARK_PANEL}; border:1px solid {DARK_BORDER};"
            f"border-radius:6px; padding:12px 16px;"
            f"font-size:12px; color:{TEXT}; line-height:1.6;"
        )
        self._logic_desc_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        logic_layout.addWidget(self._logic_desc_label)

        self.logic_panel.hide()
        outer.addWidget(self.logic_panel, stretch=1)

    # ── 테마 ──────────────────────────────────────

    def _build_tab1(self):
        _cfg = load_config()
        is_host = (_cfg.get("role", "guest") == "host")
        # ── Tab 1: 기본 설정 ──────────────────────
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        tab1_layout.setContentsMargins(16, 16, 16, 16)
        tab1_layout.setSpacing(8)
        self.tabs.addTab(tab1, "기본 설정")

        LWIDTH = 72  # label column width

        # JNLoader 경로
        r0 = QHBoxLayout()
        lbl0 = QLabel("JNLoader"); lbl0.setFixedWidth(LWIDTH)
        r0.addWidget(lbl0)
        self.edit_path = QLineEdit(_cfg.get("jnloader_path", ""))
        self.edit_path.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.edit_path.editingFinished.connect(self._save_path)
        r0.addWidget(self.edit_path)
        btn_browse = QPushButton("찾기"); btn_browse.setFixedWidth(62)
        btn_browse.clicked.connect(self._browse)
        r0.addWidget(btn_browse)
        tab1_layout.addLayout(r0)

        # 화면 모드 (풀스크린 / 창모드) - FHD 초과에서만 활성화
        r0b = QHBoxLayout()
        lbl0b = QLabel("화면 모드"); lbl0b.setFixedWidth(LWIDTH)
        r0b.addWidget(lbl0b)
        self.rb_fullscreen = QRadioButton("풀스크린")
        self.rb_windowed   = QRadioButton("창모드")
        _mon_w = ctypes.windll.user32.GetSystemMetrics(0)
        _mon_h = ctypes.windll.user32.GetSystemMetrics(1)
        _above_fhd = (_mon_w > 1920 or _mon_h > 1080)
        if _above_fhd:
            # FHD 초과: 풀스크린 / 창모드 선택 가능
            _saved_wmode = _cfg.get("wc3_window_mode", "fullscreen")
            if _saved_wmode == "fullscreen":
                self.rb_fullscreen.setChecked(True)
            else:
                self.rb_windowed.setChecked(True)
            self.rb_fullscreen.setEnabled(True)
            self.rb_windowed.setEnabled(True)
        else:
            # FHD 이하: 풀스크린 고정, 선택 불가
            self.rb_fullscreen.setChecked(True)
            self.rb_fullscreen.setEnabled(False)
            self.rb_windowed.setEnabled(False)
            self.rb_fullscreen.setToolTip("FHD(1920×1080) 이하 모니터는 풀스크린 고정")
            self.rb_windowed.setToolTip("FHD(1920×1080) 이하 모니터는 풀스크린 고정")
        self.rb_fullscreen.toggled.connect(self._on_wmode_changed)
        self.rb_windowed.toggled.connect(self._on_wmode_changed)
        r0b.addWidget(self.rb_fullscreen)
        r0b.addWidget(self.rb_windowed)
        r0b.addStretch()
        tab1_layout.addLayout(r0b)

        # 포지션 (방장 / 승객 / 프리매치)
        r1 = QHBoxLayout()
        lbl1 = QLabel("포지션"); lbl1.setFixedWidth(LWIDTH)
        r1.addWidget(lbl1)
        self.bg_role      = QButtonGroup(self)
        self.rb_host      = QRadioButton("방장")
        self.rb_guest     = QRadioButton("승객")
        self.rb_freematch = QRadioButton("프리매치 - 공개 룸리스트 참여")
        _role = _cfg.get("role", "freematch")
        self.rb_host.setChecked(_role == "host")
        self.rb_guest.setChecked(_role == "guest")
        self.rb_freematch.setChecked(_role == "freematch")
        self.bg_role.addButton(self.rb_host,      0)
        self.bg_role.addButton(self.rb_guest,     1)
        self.bg_role.addButton(self.rb_freematch, 2)
        self.rb_host.toggled.connect(self._on_role_changed)
        self.rb_freematch.toggled.connect(self._on_role_changed)
        r1.addWidget(self.rb_host)
        r1.addWidget(self.rb_guest)
        _sep_r1 = QFrame(); _sep_r1.setFrameShape(QFrame.VLine)
        _sep_r1.setStyleSheet(f"color:{DARK_BORDER};")
        _sep_r1.setFixedWidth(16)
        r1.addWidget(_sep_r1)
        r1.addWidget(self.rb_freematch)
        r1.addStretch()
        tab1_layout.addLayout(r1)

        # ── 프리매치 필터 패널 ────────────────────────────────────────────────
        self._fm_panel = QFrame()
        fm_layout = QVBoxLayout(self._fm_panel)
        fm_layout.setContentsMargins(0, 4, 0, 4)
        fm_layout.setSpacing(6)
        fm_r1 = QHBoxLayout()
        fm_lbl1 = QLabel("방 제목"); fm_lbl1.setFixedWidth(LWIDTH)
        fm_r1.addWidget(fm_lbl1)
        self.edit_fm_room = QLineEdit(_cfg.get("fm_room_name", ""))
        self.edit_fm_room.setPlaceholderText("포함 문자열 (비워두면 전체)")
        self.edit_fm_room.editingFinished.connect(
            lambda: update_config("fm_room_name", self.edit_fm_room.text()))
        fm_r1.addWidget(self.edit_fm_room)
        fm_layout.addLayout(fm_r1)
        fm_r2 = QHBoxLayout()
        fm_lbl2 = QLabel("방 장"); fm_lbl2.setFixedWidth(LWIDTH)
        fm_r2.addWidget(fm_lbl2)
        self.edit_fm_host = QLineEdit(_cfg.get("fm_host", ""))
        self.edit_fm_host.setPlaceholderText("포함 문자열 (비워두면 전체)")
        self.edit_fm_host.editingFinished.connect(
            lambda: update_config("fm_host", self.edit_fm_host.text()))
        fm_r2.addWidget(self.edit_fm_host)
        fm_layout.addLayout(fm_r2)
        fm_r3 = QHBoxLayout()
        fm_lbl3 = QLabel("맵 이름"); fm_lbl3.setFixedWidth(LWIDTH)
        fm_r3.addWidget(fm_lbl3)
        self.edit_fm_map = QLineEdit(_cfg.get("fm_map_name", "NOX RPG"))
        self.edit_fm_map.setPlaceholderText("맵 이름 키워드")
        self.edit_fm_map.editingFinished.connect(
            lambda: update_config("fm_map_name", self.edit_fm_map.text()))
        fm_r3.addWidget(self.edit_fm_map)
        fm_layout.addLayout(fm_r3)
        fm_r4 = QHBoxLayout()
        fm_lbl4 = QLabel("최대 인원"); fm_lbl4.setFixedWidth(LWIDTH)
        fm_r4.addWidget(fm_lbl4)
        self.spn_fm_max = QSpinBox()
        self.spn_fm_max.setRange(1, 24)
        self.spn_fm_max.setValue(_cfg.get("fm_max_players", 6))
        self.spn_fm_max.setSuffix("인 이상 제외")
        self.spn_fm_max.setFixedWidth(110)
        self.spn_fm_max.valueChanged.connect(
            lambda v: update_config("fm_max_players", v))
        if "fm_max_players" not in _cfg:
            update_config("fm_max_players", 6)
        fm_r4.addWidget(self.spn_fm_max)
        fm_r4.addStretch()
        fm_layout.addLayout(fm_r4)
        self._fm_panel.setVisible(_role == "freematch")
        tab1_layout.addWidget(self._fm_panel)

        # 토글 행 (비공개방 / 자동시작 / 인원 수)
        r2 = QHBoxLayout()
        _tog_pad = QLabel(); _tog_pad.setFixedWidth(LWIDTH)
        r2.addWidget(_tog_pad)
        self.tog_private = ToggleSwitch(_cfg.get("room_private", False))
        self.tog_private.setEnabled(is_host)
        self.tog_private.toggled.connect(self._on_private_toggled)
        r2.addWidget(self.tog_private)
        self.lbl_priv = QLabel("비공개방")
        r2.addWidget(self.lbl_priv)
        r2.addSpacing(18)
        self.tog_auto = ToggleSwitch(_cfg.get("auto_start", False))
        self.tog_auto.setEnabled(is_host)
        self.tog_auto.toggled.connect(self._on_auto_toggled)
        r2.addWidget(self.tog_auto)
        self.lbl_auto = QLabel("자동시작")
        r2.addWidget(self.lbl_auto)
        r2.addSpacing(8)
        self.spn_count = ConfigSpinBox("auto_start_count", 1, 12, 6, suffix="명", width=66)
        self.spn_count.setEnabled(is_host and _cfg.get("auto_start", False))
        r2.addWidget(self.spn_count)
        r2.addSpacing(8)
        self.lbl_as_timeout = QLabel("타임아웃")
        r2.addWidget(self.lbl_as_timeout)
        r2.addSpacing(4)
        self.spn_as_timeout = QSpinBox()
        self.spn_as_timeout.setRange(0, 9999)
        self.spn_as_timeout.setValue(_cfg.get("auto_start_timeout", 180))
        self.spn_as_timeout.setSuffix("초")
        self.spn_as_timeout.setSpecialValueText("∞")   # 0 → 무제한
        self.spn_as_timeout.setFixedWidth(80)
        self.spn_as_timeout.setEnabled(is_host and _cfg.get("auto_start", False))
        self.spn_as_timeout.valueChanged.connect(self._on_as_timeout_changed)
        if "auto_start_timeout" not in _cfg:
            self._on_as_timeout_changed(self.spn_as_timeout.value())
        r2.addWidget(self.spn_as_timeout)
        r2.addStretch()
        tab1_layout.addLayout(r2)

        # !dr 딜레이 설정 (방장 전용)
        r2b = QHBoxLayout()
        _dr_pad = QLabel(); _dr_pad.setFixedWidth(LWIDTH)
        r2b.addWidget(_dr_pad)
        self.lbl_dr = QLabel("Delay Reduce")
        r2b.addWidget(self.lbl_dr)
        r2b.addSpacing(8)
        self.spn_dr = QSpinBox()
        self.spn_dr.setRange(0, 550)
        self.spn_dr.setValue(_cfg.get("dr_delay", 15))
        self.spn_dr.setSuffix("ms")
        self.spn_dr.setFixedWidth(80)
        self.spn_dr.setEnabled(is_host)
        self.spn_dr.valueChanged.connect(self._on_dr_changed)
        if "dr_delay" not in _cfg:
            update_config("dr_delay", 15)
        r2b.addWidget(self.spn_dr)
        r2b.addStretch()
        tab1_layout.addLayout(r2b)

        # 방 제목
        r3 = QHBoxLayout()
        self.lbl_room = QLabel("방 제목"); self.lbl_room.setFixedWidth(LWIDTH)
        r3.addWidget(self.lbl_room)
        self.edit_room = QLineEdit(_cfg.get("room_name", ""))
        self.edit_room.setPlaceholderText("방 제목 입력")
        self.edit_room.editingFinished.connect(self._save_room_name)
        self.edit_room.setEnabled(_role != "freematch")
        self.lbl_room.setEnabled(_role != "freematch")
        if _role == "freematch":
            self.lbl_room.setStyleSheet(f"color:{TEXT_DIM};")
        r3.addWidget(self.edit_room)
        tab1_layout.addLayout(r3)

        # 비밀번호 (인라인)
        r4 = QHBoxLayout()
        lbl4 = QLabel("비밀번호"); lbl4.setFixedWidth(LWIDTH)
        r4.addWidget(lbl4)
        self.edit_pw = QLineEdit(decrypt_password(_cfg.get("bnet_password", "")))
        self.edit_pw.setEchoMode(QLineEdit.Password)
        self.edit_pw.setPlaceholderText("Battle.net 비밀번호")
        self.edit_pw.editingFinished.connect(self._save_password)
        r4.addWidget(self.edit_pw)
        self.btn_eye = QPushButton("👁"); self.btn_eye.setFixedWidth(40)
        self.btn_eye.setCheckable(True)
        self.btn_eye.clicked.connect(self._toggle_pw)
        r4.addWidget(self.btn_eye)
        tab1_layout.addLayout(r4)

        sep_pw = QFrame(); sep_pw.setFrameShape(QFrame.HLine)
        sep_pw.setStyleSheet(f"color:{DARK_BORDER};")
        tab1_layout.addWidget(sep_pw)

        # 인게임 이벤트 감지 시 재시작 옵션
        self.chk_ingame_restart = ConfigCheckBox(
            "ingame_restart_on_event",
            "(페이탈 및 리방 매크로) 플레이어가 나가거나 미션 종료 시 -save 후 게임 재시작",
            True,
        )
        tab1_layout.addWidget(self.chk_ingame_restart)

        # 자동 세이브 시스템
        r_autosave = QHBoxLayout()
        self.chk_auto_save = ConfigCheckBox("auto_save_enabled", "자동 세이브 시스템", True)
        r_autosave.addWidget(self.chk_auto_save)
        self.spn_auto_save = QSpinBox()
        self.spn_auto_save.setRange(300, 99999)
        self.spn_auto_save.setValue(_cfg.get("auto_save_interval", 300))
        self.spn_auto_save.setSuffix("초")
        self.spn_auto_save.setFixedWidth(80)
        self.spn_auto_save.editingFinished.connect(self._on_auto_save_interval_changed)
        r_autosave.addWidget(self.spn_auto_save)
        lbl_autosave = QLabel("- 인게임 접속 시 설정한 초마다 자동 -save 진행")
        lbl_autosave.setStyleSheet(f"color:{TEXT_DIM};")
        r_autosave.addWidget(lbl_autosave)
        r_autosave.addStretch()
        tab1_layout.addLayout(r_autosave)

        # 스마트키
        r_smart = QHBoxLayout()
        self.chk_smart_key = ConfigCheckBox("smart_key_enabled", "스마트키", False)
        self.chk_smart_key.toggled.connect(self._on_smart_key_toggled)
        r_smart.addWidget(self.chk_smart_key)
        lbl_smart = QLabel("- Q W E R T / A D F G / Z X C V 사용 시 영웅 부대지정 자동 선택 (채팅 중 제외)")
        lbl_smart.setStyleSheet(f"color:{TEXT_DIM};")
        r_smart.addWidget(lbl_smart)
        r_smart.addStretch()
        tab1_layout.addLayout(r_smart)

        # 채팅 커맨드 키매핑 (2줄)
        _CMD_CHK_W = 80  # 채팅 커맨드 체크박스 가로폭 통일

        self.chk_cmd_suicide = QCheckBox("-suicide")
        self.chk_cmd_suicide.setChecked(_cfg.get("cmd_suicide_enabled", False))
        self.chk_cmd_suicide.setFixedWidth(_CMD_CHK_W)
        self.dd_cmd_suicide  = HotkeyDropdown(_ALL_KEYS)
        self.dd_cmd_suicide.setCurrentText(_cfg.get("cmd_suicide_key", "Num *"))
        self.dd_cmd_suicide.setFixedSize(160, 30)

        self.chk_cmd_save = QCheckBox("-save")
        self.chk_cmd_save.setChecked(_cfg.get("cmd_save_enabled", False))
        self.chk_cmd_save.setFixedWidth(_CMD_CHK_W)
        self.dd_cmd_save  = HotkeyDropdown(_ALL_KEYS)
        self.dd_cmd_save.setCurrentText(_cfg.get("cmd_save_key", "Num /"))
        self.dd_cmd_save.setFixedSize(160, 30)

        self.chk_cmd_effect = QCheckBox("-이펙트")
        self.chk_cmd_effect.setChecked(_cfg.get("cmd_effect_enabled", False))
        self.chk_cmd_effect.setFixedWidth(_CMD_CHK_W)
        self.dd_cmd_effect  = HotkeyDropdown(_ALL_KEYS)
        self.dd_cmd_effect.setCurrentText(_cfg.get("cmd_effect_key", "Num -"))
        self.dd_cmd_effect.setFixedSize(160, 30)

        self.chk_cmd_exit = QCheckBox("-exit")
        self.chk_cmd_exit.setChecked(_cfg.get("cmd_exit_enabled", False))
        self.chk_cmd_exit.setFixedWidth(_CMD_CHK_W)
        self.dd_cmd_exit  = HotkeyDropdown(_ALL_KEYS)
        self.dd_cmd_exit.setCurrentText(_cfg.get("cmd_exit_key", "Num +"))
        self.dd_cmd_exit.setFixedSize(160, 30)

        r_chatcmd1 = QHBoxLayout()
        r_chatcmd1.addWidget(self.chk_cmd_suicide)
        r_chatcmd1.addWidget(self.dd_cmd_suicide)
        r_chatcmd1.addSpacing(12)
        r_chatcmd1.addWidget(self.chk_cmd_save)
        r_chatcmd1.addWidget(self.dd_cmd_save)
        r_chatcmd1.addStretch()
        tab1_layout.addLayout(r_chatcmd1)

        r_chatcmd2 = QHBoxLayout()
        r_chatcmd2.addWidget(self.chk_cmd_effect)
        r_chatcmd2.addWidget(self.dd_cmd_effect)
        r_chatcmd2.addSpacing(12)
        r_chatcmd2.addWidget(self.chk_cmd_exit)
        r_chatcmd2.addWidget(self.dd_cmd_exit)
        r_chatcmd2.addStretch()
        tab1_layout.addLayout(r_chatcmd2)

        self.chk_cmd_suicide.toggled.connect(lambda _: self._on_chat_cmd_changed())
        self.dd_cmd_suicide.selectionChanged.connect(lambda _: self._on_chat_cmd_changed())
        self.chk_cmd_save.toggled.connect(lambda _: self._on_chat_cmd_changed())
        self.dd_cmd_save.selectionChanged.connect(lambda _: self._on_chat_cmd_changed())
        self.chk_cmd_effect.toggled.connect(lambda _: self._on_chat_cmd_changed())
        self.dd_cmd_effect.selectionChanged.connect(lambda _: self._on_chat_cmd_changed())
        self.chk_cmd_exit.toggled.connect(lambda _: self._on_exit_cmd_changed())
        self.dd_cmd_exit.selectionChanged.connect(lambda _: self._on_exit_cmd_changed())

        sep_log = QFrame(); sep_log.setFrameShape(QFrame.HLine)
        sep_log.setStyleSheet(f"color:{DARK_BORDER};")
        tab1_layout.addWidget(sep_log)

        self.btn_hotkey = QPushButton("⌨  시작키/중지키 설정")
        self.btn_hotkey.setFixedHeight(30)
        self.btn_hotkey.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.btn_hotkey.clicked.connect(self._open_hotkey_dialog)
        tab1_layout.addWidget(self.btn_hotkey)

        self.btn_log_toggle = QPushButton("로그")
        self.btn_log_toggle.setFixedHeight(30)
        self.btn_log_toggle.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.btn_log_toggle.setCheckable(True)
        self.btn_log_toggle.setChecked(False)
        self.btn_log_toggle.clicked.connect(self._toggle_log_panel)
        tab1_layout.addWidget(self.btn_log_toggle)

        _overlay_on = _cfg.get("overlay_enabled", True)
        self.btn_overlay_toggle = QPushButton(
            "이미지 서치 오버레이: ON" if _overlay_on else "이미지 서치 오버레이: OFF")
        self.btn_overlay_toggle.setFixedHeight(30)
        self.btn_overlay_toggle.setCheckable(True)
        self.btn_overlay_toggle.setChecked(_overlay_on)
        if _overlay_on:
            self.btn_overlay_toggle.setStyleSheet(
                f"background-color:{RED}; color:#ffffff; font-weight:bold;"
                f"border:none; border-radius:6px; padding:4px 12px;"
            )
        self.btn_overlay_toggle.clicked.connect(self._on_overlay_toggled)
        tab1_layout.addWidget(self.btn_overlay_toggle)

        _unclip_on = _cfg.get("mouse_unclip", False)
        self.btn_unclip_toggle = QPushButton(
            "마우스 감금 해제: ON" if _unclip_on else "마우스 감금 해제: OFF")
        self.btn_unclip_toggle.setFixedHeight(30)
        self.btn_unclip_toggle.setCheckable(True)
        self.btn_unclip_toggle.setChecked(_unclip_on)
        if _unclip_on:
            self.btn_unclip_toggle.setStyleSheet(
                f"background-color:{RED}; color:#ffffff; font-weight:bold;"
                f"border:none; border-radius:6px; padding:4px 12px;"
            )
        self.btn_unclip_toggle.clicked.connect(self._on_unclip_toggled)
        tab1_layout.addWidget(self.btn_unclip_toggle)

        _topmost_on = _cfg.get("topmost", True)
        self.btn_topmost_toggle = QPushButton(
            "항상 위: ON" if _topmost_on else "항상 위: OFF")
        self.btn_topmost_toggle.setFixedHeight(30)
        self.btn_topmost_toggle.setCheckable(True)
        self.btn_topmost_toggle.setChecked(_topmost_on)
        if _topmost_on:
            self.btn_topmost_toggle.setStyleSheet(
                f"background-color:{RED}; color:#ffffff; font-weight:bold;"
                f"border:none; border-radius:6px; padding:4px 12px;"
            )
        self.btn_topmost_toggle.clicked.connect(self._on_topmost_toggled)
        tab1_layout.addWidget(self.btn_topmost_toggle)

        tab1_layout.addStretch()


    def _build_tab2(self):
        _cfg = load_config()
        # ── Tab 2: 캐릭터 선택 ────────────────────────
        saved_char = _cfg.get("character", next(iter(_CHAR_IMAGES)))

        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)
        tab2_layout.setContentsMargins(16, 16, 16, 16)
        tab2_layout.setSpacing(12)
        self.tabs.addTab(tab2, "인게임 세팅")

        char_title = QLabel("캐릭터 선택")
        char_title.setStyleSheet(f"color:{ACCENT}; font-size:13px; font-weight:bold;")
        tab2_layout.addWidget(char_title)

        sep_char = QFrame(); sep_char.setFrameShape(QFrame.HLine)
        sep_char.setStyleSheet(f"color:{DARK_BORDER};")
        tab2_layout.addWidget(sep_char)

        self.bg_char = QButtonGroup(self)
        char_row = QHBoxLayout()
        char_row.setSpacing(16)
        for i, char_name in enumerate(_CHAR_IMAGES):
            rb = QRadioButton(char_name)
            rb.setChecked(char_name == saved_char)
            self.bg_char.addButton(rb, i)
            char_row.addWidget(rb)
        char_row.addStretch()
        tab2_layout.addLayout(char_row)
        self.bg_char.buttonClicked.connect(self._on_character_changed)

        # 출석체크
        sep_att = QFrame(); sep_att.setFrameShape(QFrame.HLine)
        sep_att.setStyleSheet(f"color:{DARK_BORDER};")
        tab2_layout.addWidget(sep_att)

        att_title = QLabel("출석체크")
        att_title.setStyleSheet(f"color:{ACCENT}; font-size:13px; font-weight:bold;")
        tab2_layout.addWidget(att_title)

        self.chk_attendance = ConfigCheckBox("attendance_check", "출석체크 활성화", True)
        tab2_layout.addWidget(self.chk_attendance)

        # 자동사냥 설정
        sep_hunt = QFrame(); sep_hunt.setFrameShape(QFrame.HLine)
        sep_hunt.setStyleSheet(f"color:{DARK_BORDER};")
        tab2_layout.addWidget(sep_hunt)

        hunt_title = QLabel("자동사냥 설정")
        hunt_title.setStyleSheet(f"color:{ACCENT}; font-size:13px; font-weight:bold;")
        tab2_layout.addWidget(hunt_title)

        self.chk_auto_hunt = ConfigCheckBox("auto_hunt", "자동사냥 활성화", False)
        tab2_layout.addWidget(self.chk_auto_hunt)

        self.chk_stay_hunt = ConfigCheckBox(
            "stay_hunt",
            "제자리 사냥 : 체크시 제자리 사냥에 체크함. 체크를 풀면 제자리 사냥 체크 해제",
            False,
        )
        tab2_layout.addWidget(self.chk_stay_hunt)

        hunt_radius_row = QHBoxLayout()
        hunt_radius_row.setSpacing(8)
        self.lbl_hunt_radius = QLabel("사냥반경")
        hunt_radius_row.addWidget(self.lbl_hunt_radius)
        self.spn_hunt_radius = QSpinBox()
        self.spn_hunt_radius.setRange(0, 3000)
        self.spn_hunt_radius.setSingleStep(100)
        self.spn_hunt_radius.setValue(_cfg.get("hunt_radius", 1000))
        self.spn_hunt_radius.setFixedWidth(90)
        def _clamp_hunt_radius():
            raw = self.spn_hunt_radius.value()
            clamped = max(500, min(3000, round(raw / 100) * 100))
            if self.spn_hunt_radius.value() != clamped:
                self.spn_hunt_radius.setValue(clamped)
            le = self.spn_hunt_radius.lineEdit()
            le.setCursorPosition(len(le.text()))
        self.spn_hunt_radius.editingFinished.connect(_clamp_hunt_radius)
        hunt_radius_row.addWidget(self.spn_hunt_radius)
        hunt_radius_row.addStretch()
        tab2_layout.addLayout(hunt_radius_row)

        # 자동사냥 활성화 여부에 따라 하위 위젯 활성/비활성
        def _update_hunt_children(enabled: bool):
            self.chk_stay_hunt.setEnabled(enabled)
            self.lbl_hunt_radius.setEnabled(enabled)
            self.spn_hunt_radius.setEnabled(enabled)

        _update_hunt_children(self.chk_auto_hunt.isChecked())
        self.chk_auto_hunt.toggled.connect(_update_hunt_children)
        self.spn_hunt_radius.valueChanged.connect(
            lambda v: update_config("hunt_radius", v)
            if v % 100 == 0 else None
        )
        if "hunt_radius" not in _cfg:
            update_config("hunt_radius", 1000)
        self.chk_auto_hunt.toggled.connect(lambda _: self._refresh_logic_panel())
        self.chk_stay_hunt.toggled.connect(lambda _: self._refresh_logic_panel())
        self.spn_hunt_radius.valueChanged.connect(lambda _: self._refresh_logic_panel())

        # 부대지정
        sep_group = QFrame(); sep_group.setFrameShape(QFrame.HLine)
        sep_group.setStyleSheet(f"color:{DARK_BORDER};")
        tab2_layout.addWidget(sep_group)

        group_title = QLabel("부대지정")
        group_title.setStyleSheet(f"color:{ACCENT}; font-size:13px; font-weight:bold;")
        tab2_layout.addWidget(group_title)

        self.chk_control_group = ConfigCheckBox("control_group_enabled", "부대지정 활성화", True)
        tab2_layout.addWidget(self.chk_control_group)

        group_row = QHBoxLayout()
        group_row.setSpacing(8)

        self.lbl_hero_group = QLabel("영웅")
        group_row.addWidget(self.lbl_hero_group)
        self.spn_hero_group = QSpinBox()
        self.spn_hero_group.setRange(0, 9)
        self.spn_hero_group.setValue(_cfg.get("hero_group", 1))
        self.spn_hero_group.setSuffix("번")
        self.spn_hero_group.setFixedWidth(72)
        group_row.addWidget(self.spn_hero_group)

        group_row.addSpacing(24)

        self.lbl_storage_group = QLabel("창고")
        group_row.addWidget(self.lbl_storage_group)
        self.spn_storage_group = QSpinBox()
        self.spn_storage_group.setRange(0, 9)
        self.spn_storage_group.setValue(_cfg.get("storage_group", 2))
        self.spn_storage_group.setSuffix("번")
        self.spn_storage_group.setFixedWidth(72)
        group_row.addWidget(self.spn_storage_group)

        group_row.addStretch()
        tab2_layout.addLayout(group_row)

        def _update_group_children(enabled: bool):
            self.lbl_hero_group.setEnabled(enabled)
            self.spn_hero_group.setEnabled(enabled)
            self.lbl_storage_group.setEnabled(enabled)
            self.spn_storage_group.setEnabled(enabled)

        _update_group_children(self.chk_control_group.isChecked())
        self.chk_control_group.toggled.connect(_update_group_children)
        tab2_layout.addStretch()

        self.spn_hero_group.valueChanged.connect(self._on_hero_group_changed)
        self.spn_storage_group.valueChanged.connect(self._on_storage_group_changed)
        if "hero_group" not in _cfg:
            update_config("hero_group", 1)
        if "storage_group" not in _cfg:
            update_config("storage_group", 2)


    def _build_tab3(self):
        # ── Tab 3: 일반 사냥터 ────────────────────────
        _cfg3 = load_config()
        tab3 = QWidget()
        tab3_layout = QVBoxLayout(tab3)
        tab3_layout.setSpacing(10)
        tab3_layout.setContentsMargins(16, 16, 16, 16)

        self.rb_normal_hunt = QRadioButton("일반 사냥터 활성화")
        self.rb_normal_hunt.setChecked(_cfg3.get("normal_hunt_enabled", True))
        tab3_layout.addWidget(self.rb_normal_hunt)

        sep_nh = QFrame(); sep_nh.setFrameShape(QFrame.HLine)
        sep_nh.setStyleSheet(f"color:{DARK_BORDER};")
        tab3_layout.addWidget(sep_nh)

        _PORTAL_KEYS = ["Q 포탈 | 라하린 숲", "W 포탈 | 아스탈 요새", "E 포탈 | 어둠얼음성채", "R 포탈 | 버려진 고성",
                        "A 포탈 | 바위협곡", "S 포탈 | 바람의 협곡", "D 포탈 | 시계태엽 공장", "F 포탈 | 속삭임의 숲",
                        "Z 포탈 | 이그니스영역", "X 포탈 | 정령계"]
        portal_row_nh = QHBoxLayout()
        portal_row_nh.addWidget(QLabel("포탈 진입:"))
        self.combo_nh_portal_key = HotkeyDropdown(_PORTAL_KEYS)
        self.combo_nh_portal_key.setFixedSize(200, 30)
        self.combo_nh_portal_key.install_portal_align()
        _saved_nh_key = _cfg3.get("normal_hunt_portal_key", "Q 포탈 | 라하린 숲")
        self.combo_nh_portal_key.setCurrentText(_saved_nh_key)
        def _update_zone_frames():
            _action      = _nh_action_grp.checkedId()
            _key         = self.combo_nh_portal_key.currentText()
            _boss_active = self.chk_nh_action_3.isChecked()
            _ext_boss_on = self.chk_nh_action_4.isChecked()

            # boss-only 판단: 보스 체크 O + 타이머 OFF → 사냥 없이 보스만 반복
            _cur_bp    = self._nh_boss_panels.get(_key)
            _any_boss  = (_cur_bp is not None and
                          any(chk.isChecked() for _, chk in _cur_bp._boss_chks))
            _timer_on  = ((_cur_bp._chk_boss_timer is not None and
                           _cur_bp._chk_boss_timer.isChecked())
                          if _cur_bp else False)
            _boss_only = _boss_active and _any_boss and not _timer_on and not _ext_boss_on

            # 액션 0/1/2 라디오: boss_only면 비활성화
            self.rb_nh_action_0.setEnabled(not _boss_only)
            self.rb_nh_action_1.setEnabled(not _boss_only)
            self.rb_nh_action_2.setEnabled(not _boss_only)

            # 구역 서브패널 (boss_only면 강제 숨김)
            for _pcfg in PORTAL_CONFIGS:
                self._portal_widgets[_pcfg.name].setVisible(
                    not _boss_only and _action == 1 and _key == _pcfg.name
                )
            # 커스텀 좌표 패널 (boss_only면 강제 숨김)
            self._nh_custom_panel.setVisible(not _boss_only and _action == 2)

            # 보스 패널 (액션3 체크 + 해당 포탈 키 + 액션4 OFF일 때만 표시)
            for _pcfg in PORTAL_CONFIGS:
                if _pcfg.name in self._nh_boss_panels:
                    _panel = self._nh_boss_panels[_pcfg.name]
                    _vis   = _boss_active and _key == _pcfg.name and not _ext_boss_on
                    _panel.setVisible(_vis)
                    if _vis:
                        _panel.sync_ui()
            # 액션4 서브패널 show/hide + 내부 위젯 sync
            if hasattr(self, "_nh_ext_boss_sub"):
                self._nh_ext_boss_sub.setVisible(_ext_boss_on)
                if _ext_boss_on:
                    _ext_t = self._chk_ext_timer.isChecked()
                    self._led_ext_timer.setEnabled(_ext_t)
                    self._chk_ext_priority.setEnabled(_ext_t)
                    self._chk_ext_priority.setStyleSheet(
                        f"color:{YELLOW}; font-weight:bold;" if _ext_t else f"color:{TEXT_DIM};"
                    )

            # Logic 설명 갱신
            self._refresh_logic_panel()
        self.combo_nh_portal_key.selectionChanged.connect(lambda t: (
            update_config("normal_hunt_portal_key", t),
            _update_zone_frames(),
        ))
        portal_row_nh.addWidget(self.combo_nh_portal_key)
        portal_row_nh.addStretch()
        tab3_layout.addLayout(portal_row_nh)

        sep_nh2 = QFrame(); sep_nh2.setFrameShape(QFrame.HLine)
        sep_nh2.setStyleSheet(f"color:{DARK_BORDER};")
        tab3_layout.addWidget(sep_nh2)

        _hint_off = (f": 제자리 사냥을 <b><span style='color:{RED}'>하는것을 추천 (</span>"
                     f"<span style='color:{GREEN}'><b>OFF</b></span>"
                     f"<span style='color:{RED}'><b> 권장)</b></span></b>")
        _hint_on  = (f": 제자리 사냥을 <b><span style='color:{RED}'>하는것을 추천 (</span>"
                     f"<span style='color:{GREEN}'><b>ON</b></span>"
                     f"<span style='color:{RED}'><b> 권장)</b></span></b>")

        _nh_saved_action = _cfg3.get("normal_hunt_action", 0)

        def _make_action_row(rb, hint_html=None):
            row = QHBoxLayout()
            row.setSpacing(4)
            row.addWidget(rb)
            if hint_html:
                lbl = QLabel(hint_html)
                lbl.setTextFormat(Qt.RichText)
                lbl.setStyleSheet("background:transparent;")
                row.addWidget(lbl)
            row.addStretch()
            return row

        self.rb_nh_action_0 = QRadioButton("포탈 진입 후 즉시 해당 맵 자동사냥 진행")
        self.rb_nh_action_1 = QRadioButton("포탈 진입 후 특정 구역으로 이동해서 자동사냥 진행")
        self.rb_nh_action_2 = QRadioButton("포탈 진입 후 커스텀 좌표 이동해서 자동사냥 진행")

        [self.rb_nh_action_0, self.rb_nh_action_1,
         self.rb_nh_action_2][_nh_saved_action].setChecked(True)

        _nh_hint_off = (f"<b><span style='color:{RED}'>: 제자리 사냥을 </span>"
                        f"<span style='color:{GREEN}'>OFF</span>"
                        f"<span style='color:{RED}'> 하는것을 추천</span></b>")
        _nh_hint_on  = (f"<b><span style='color:{RED}'>: 제자리 사냥을 </span>"
                        f"<span style='color:{GREEN}'>ON</span>"
                        f"<span style='color:{RED}'> 하는것을 추천</span></b>")

        tab3_layout.addLayout(_make_action_row(self.rb_nh_action_0, _nh_hint_off))
        tab3_layout.addLayout(_make_action_row(self.rb_nh_action_1, _nh_hint_on))

        # ── 구역 서브패널 (PortalZoneWidget × 10) ─────────────────────────
        self._portal_widgets: "dict[str, PortalZoneWidget]" = {}
        for _pcfg in PORTAL_CONFIGS:
            _pw = PortalZoneWidget(_pcfg)
            self._portal_widgets[_pcfg.name] = _pw
            _pw.setVisible(_nh_saved_action == 1 and _saved_nh_key == _pcfg.name)
            _pw.zone_changed.connect(_update_zone_frames)
            tab3_layout.addWidget(_pw)

        # ────────────────────────────────────────────────────────────

        tab3_layout.addLayout(_make_action_row(self.rb_nh_action_2))

        self._nh_custom_panel = _CustomCoordsPanel("nh_custom_coords")
        self._nh_custom_panel.setVisible(_nh_saved_action == 2)
        tab3_layout.addWidget(self._nh_custom_panel)

        # ── 액션3: 필드보스 (독립 체크박스) ──────────────────────────────
        _sep_boss_act = QFrame(); _sep_boss_act.setFrameShape(QFrame.HLine)
        _sep_boss_act.setStyleSheet(f"color:{DARK_BORDER};")
        tab3_layout.addWidget(_sep_boss_act)

        self.chk_nh_action_3 = QCheckBox("포탈 진입 후 필드보스 진행")
        self.chk_nh_action_3.setChecked(_cfg3.get("normal_hunt_boss_enabled", False))

        def _on_a3_changed(s):
            update_config("normal_hunt_boss_enabled", bool(s))
            if s:
                self.chk_nh_action_4.blockSignals(True)
                self.chk_nh_action_4.setChecked(False)
                self.chk_nh_action_4.blockSignals(False)
                update_config("normal_hunt_ext_boss_enabled", False)
            _update_zone_frames()

        self.chk_nh_action_3.stateChanged.connect(_on_a3_changed)
        tab3_layout.addWidget(self.chk_nh_action_3)

        # ── 보스 패널 (액션3 체크 + 포탈 키에 따라 표시) ─────────────────
        self._nh_boss_panels: "dict[str, PortalBossPanel]" = {}
        for _pcfg in PORTAL_CONFIGS:
            if _pcfg.boss_defs:
                _bp = PortalBossPanel(_pcfg)
                self._nh_boss_panels[_pcfg.name] = _bp
                _bp.setVisible(_saved_nh_key == _pcfg.name)
                _bp.boss_state_changed.connect(_update_zone_frames)
                tab3_layout.addWidget(_bp)

        # ── 액션4: 외부 보스 순환 (독립 체크박스) ──────────────────────────
        self.chk_nh_action_4 = QCheckBox("외부 보스 순환")
        self.chk_nh_action_4.setChecked(_cfg3.get("normal_hunt_ext_boss_enabled", False))

        def _on_a4_changed(s):
            update_config("normal_hunt_ext_boss_enabled", bool(s))
            if s:
                self.chk_nh_action_3.blockSignals(True)
                self.chk_nh_action_3.setChecked(False)
                self.chk_nh_action_3.blockSignals(False)
                update_config("normal_hunt_boss_enabled", False)
            _update_zone_frames()

        self.chk_nh_action_4.stateChanged.connect(_on_a4_changed)
        tab3_layout.addWidget(self.chk_nh_action_4)
        _lbl_ext_boss_desc = QLabel("  └─ 활성화시 이 필드 보스 대신 다른 포탈의 보스를 순환")
        _lbl_ext_boss_desc.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        tab3_layout.addWidget(_lbl_ext_boss_desc)

        # ── 액션4 서브패널 ────────────────────────────────────────────────
        self._nh_ext_boss_sub = QWidget()
        self._nh_ext_boss_sub.setStyleSheet(
            f"QWidget {{ background:{DARK_PANEL}; border:1px solid {DARK_BORDER}; border-radius:6px; }}"
            f"QLabel, QCheckBox {{ border:none; background:transparent; }}"
        )
        _ext_lay = QVBoxLayout(self._nh_ext_boss_sub)
        _ext_lay.setContentsMargins(12, 8, 12, 10)
        _ext_lay.setSpacing(5)

        # ── 외부 보스 목록 ──────────────────────────────────────────────
        _ext_lbl_list = QLabel("외부 보스 목록  (최대 5개 · 위에서부터 처치 순서)")
        _ext_lbl_list.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px; font-weight:bold;")
        _ext_lay.addWidget(_ext_lbl_list)

        # 행 컨테이너
        _ext_rows_w = QWidget()
        _ext_rows_w.setStyleSheet("background:transparent; border:none;")
        self._ext_rows_lay = QVBoxLayout(_ext_rows_w)
        self._ext_rows_lay.setContentsMargins(0, 0, 0, 0)
        self._ext_rows_lay.setSpacing(4)
        _ext_lay.addWidget(_ext_rows_w)

        self._ext_boss_rows: "list[dict]" = []
        _bportal_names = [p.name for p in PORTAL_CONFIGS if p.boss_defs]

        def _get_boss_defs(pname):
            """포탈명 → [(cfg_key, 표시명)] 반환"""
            _pc = next((p for p in PORTAL_CONFIGS if p.name == pname), None)
            if _pc:
                return [(_ck, _lbl.replace("[BOSS]  ", "").replace("[BOSS] ", "").strip())
                        for _ck, _lbl in _pc.boss_defs]
            return []

        def _repopulate_hk(dd, options, select_text=None):
            """HotkeyDropdown 항목 교체 헬퍼"""
            dd._options = list(options)
            dd._list.clear()
            for _opt in dd._options:
                _item = QListWidgetItem(_opt)
                _item.setSizeHint(QSize(dd.width() - 2, 26))
                dd._list.addItem(_item)
            dd._list.setFixedHeight(26 * min(10, max(1, len(dd._options))))
            _sel = select_text if (select_text and select_text in dd._options) \
                   else (dd._options[0] if dd._options else "")
            dd._update_text(_sel)
            dd._current = _sel

        _PLACEHOLDER = "(선택)"

        def _save_ext_boss_list():
            _data = []
            for _r in self._ext_boss_rows:
                _pn  = _r["portal_dd"].currentText()
                _bn  = _r["boss_dd"].currentText()
                _bk  = _r["key_map"].get(_bn)
                if _pn and _pn != _PLACEHOLDER and _bn and _bn != _PLACEHOLDER and _bk:
                    _data.append([_pn, _bk])
            update_config("normal_hunt_ext_boss_list", _data)
            _update_zone_frames()

        # [＋ 보스 추가] 버튼 먼저 생성 (행 생성 함수에서 참조하므로)
        self._btn_ext_add = QPushButton("＋ 보스 추가")
        self._btn_ext_add.setFixedHeight(28)
        self._btn_ext_add.setStyleSheet(
            f"QPushButton {{ background:{DARK_PANEL}; border:1px solid {ACCENT};"
            f"border-radius:4px; color:{ACCENT}; font-weight:bold; padding:0px 12px; }}"
            f"QPushButton:hover {{ background:{DARK_BG}; border-color:{ACCENT_H}; color:{ACCENT_H}; }}"
            f"QPushButton:disabled {{ border-color:{DARK_BORDER}; color:{TEXT_DIM}; }}"
        )

        def _make_ext_boss_row(portal_name=None, boss_key=None):
            if len(self._ext_boss_rows) >= 5:
                return

            # ── 중복 체크 헬퍼 ─────────────────────────────────────────
            def _is_dup(pn, bn, key_map):
                if pn == _PLACEHOLDER or bn == _PLACEHOLDER or not bn:
                    return False
                _bk = key_map.get(bn)
                if not _bk:
                    return False
                for _r in self._ext_boss_rows:
                    if _r["widget"] is row_w:
                        continue
                    if (_r["portal_dd"].currentText() == pn and
                            _r["key_map"].get(_r["boss_dd"].currentText()) == _bk):
                        return True
                return False

            row_w = QWidget()
            row_w.setStyleSheet("background:transparent; border:none;")
            row_h = QHBoxLayout(row_w)
            row_h.setContentsMargins(0, 0, 0, 0)
            row_h.setSpacing(6)

            # 포탈 드롭다운 (HotkeyDropdown) — 항상 (선택) 포함
            _portal_opts = [_PLACEHOLDER] + _bportal_names
            portal_dd = HotkeyDropdown(_portal_opts)
            portal_dd.setFixedSize(172, 30)
            if portal_name and portal_name in _bportal_names:
                portal_dd.setCurrentText(portal_name)
            # else: 기본값 (선택)

            # 보스 드롭다운 (HotkeyDropdown) + mutable key_map
            _init_defs = _get_boss_defs(portal_dd.currentText())
            _key_map   = {}
            _key_map.update({lbl: ck for ck, lbl in _init_defs})
            # 항상 (선택) 을 첫 항목으로 포함
            _init_boss_opts = [_PLACEHOLDER] + [lbl for _, lbl in _init_defs]
            boss_dd = HotkeyDropdown(_init_boss_opts)
            boss_dd.setFixedSize(200, 30)
            # 저장된 데이터 로드 시에만 실제 보스 복원
            if boss_key:
                _sel_lbl = next((lbl for ck, lbl in _init_defs if ck == boss_key), None)
                if _sel_lbl:
                    boss_dd.setCurrentText(_sel_lbl)

            # 현재 선택 상태 추적 (revert용)
            _state = {
                "portal": portal_dd.currentText(),
                "boss":   boss_dd.currentText(),
            }

            def _on_portal_changed(pname):
                # 포탈 변경 시 항상 보스를 (선택)으로 초기화
                if pname == _PLACEHOLDER:
                    _key_map.clear()
                    _repopulate_hk(boss_dd, [_PLACEHOLDER], _PLACEHOLDER)
                else:
                    _defs = _get_boss_defs(pname)
                    _key_map.clear()
                    _key_map.update({lbl: ck for ck, lbl in _defs})
                    _repopulate_hk(boss_dd, [_PLACEHOLDER] + [lbl for _, lbl in _defs], _PLACEHOLDER)
                _state["portal"] = pname
                _state["boss"]   = _PLACEHOLDER
                _save_ext_boss_list()

            def _on_boss_changed(boss_lbl):
                if _is_dup(portal_dd.currentText(), boss_lbl, _key_map):
                    QMessageBox.warning(
                        self, "중복 보스",
                        f"이미 등록된 보스입니다.\n"
                        f"포탈: {portal_dd.currentText()}  /  보스: {boss_lbl}"
                    )
                    boss_dd.setCurrentText(_state["boss"])
                    return
                _state["boss"] = boss_lbl
                _save_ext_boss_list()

            portal_dd.selectionChanged.connect(_on_portal_changed)
            boss_dd.selectionChanged.connect(_on_boss_changed)

            # 삭제 버튼: 네모 박스 + X
            del_btn = QPushButton("✕")
            del_btn.setFixedSize(28, 28)
            del_btn.setStyleSheet(
                f"QPushButton {{ background:{DARK_BG}; border:1px solid {DARK_BORDER};"
                f"border-radius:4px; color:{RED}; font-weight:bold; font-size:13px; padding:0px; }}"
                f"QPushButton:hover {{ background:{RED}; color:#fff; border-color:{RED}; }}"
            )

            row_h.addWidget(portal_dd)
            row_h.addWidget(boss_dd)
            row_h.addWidget(del_btn)
            row_h.addStretch()

            row_info = {"widget": row_w, "portal_dd": portal_dd,
                        "boss_dd": boss_dd, "key_map": _key_map}
            self._ext_boss_rows.append(row_info)
            # addWidget = 항상 기존 행 아래(하단)에 추가
            self._ext_rows_lay.addWidget(row_w)
            self._btn_ext_add.setEnabled(len(self._ext_boss_rows) < 5)

            def _on_delete():
                self._ext_boss_rows.remove(row_info)
                row_w.deleteLater()
                self._btn_ext_add.setEnabled(len(self._ext_boss_rows) < 5)
                _save_ext_boss_list()
                # 삭제 후 레이아웃이 밀리면서 커서 아래 새 버튼에 호버 미적용되는 문제 수정
                # deleteLater + 레이아웃 재배치가 끝날 때까지 기다린 후 마우스 이벤트 전송
                QTimer.singleShot(50, _refresh_hover_under_cursor)

            def _refresh_hover_under_cursor():
                _gpos = QCursor.pos()
                _w = QApplication.widgetAt(_gpos)
                if _w:
                    _lpos = QPointF(_w.mapFromGlobal(_gpos))
                    _gposf = QPointF(_gpos)
                    # QEnterEvent → WA_UnderMouse = True → CSS :hover 즉시 적용
                    QApplication.sendEvent(
                        _w,
                        QEnterEvent(_lpos, _gposf, _gposf),
                    )

            del_btn.clicked.connect(_on_delete)

        # 저장된 목록 로드 (중복 경고 없이 복원)
        for _entry in _cfg3.get("normal_hunt_ext_boss_list", [])[:5]:
            if isinstance(_entry, list) and len(_entry) == 2:
                _make_ext_boss_row(_entry[0], _entry[1])

        self._btn_ext_add.setEnabled(len(self._ext_boss_rows) < 5)
        self._btn_ext_add.clicked.connect(_make_ext_boss_row)
        _ext_lay.addWidget(self._btn_ext_add)

        # ── 구분선 ──────────────────────────────────────────────────────
        _ext_sep2 = QFrame(); _ext_sep2.setFrameShape(QFrame.HLine)
        _ext_sep2.setStyleSheet(f"border:none; border-top:1px solid {DARK_BORDER};")
        _ext_lay.addWidget(_ext_sep2)

        # 보스 타이머 행
        _ext_timer_row = QHBoxLayout()
        _ext_timer_row.setSpacing(6)
        self._chk_ext_timer = QCheckBox("보스 타이머(병렬):")
        self._chk_ext_timer.setChecked(_cfg3.get("normal_hunt_ext_boss_timer", False))
        self._chk_ext_timer.setStyleSheet(f"color:{YELLOW}; font-weight:bold;")
        self._chk_ext_timer.stateChanged.connect(lambda s: (
            update_config("normal_hunt_ext_boss_timer", bool(s)),
            _update_zone_frames(),
        ))
        _ext_timer_row.addWidget(self._chk_ext_timer)

        self._led_ext_timer = QLineEdit(str(_cfg3.get("normal_hunt_ext_boss_timer_sec", 60.0)))
        self._led_ext_timer.setFixedWidth(90)
        self._led_ext_timer.setPlaceholderText("초")
        self._led_ext_timer.setStyleSheet(
            f"background:{DARK_PANEL}; border:1px solid {DARK_BORDER};"
            f"border-radius:4px; padding:2px 6px; color:{TEXT};"
        )
        self._led_ext_timer.editingFinished.connect(lambda: (
            update_config(
                "normal_hunt_ext_boss_timer_sec",
                float(self._led_ext_timer.text()) if self._led_ext_timer.text().replace('.','',1).isdigit()
                else 60.0,
            ),
        ))
        self._led_ext_timer.textChanged.connect(lambda _: _update_zone_frames())
        _ext_timer_row.addWidget(self._led_ext_timer)

        _ext_lbl_sec = QLabel("초")
        _ext_lbl_sec.setStyleSheet(f"color:{TEXT_DIM};")
        _ext_timer_row.addWidget(_ext_lbl_sec)
        _ext_timer_row.addStretch()
        _ext_lay.addLayout(_ext_timer_row)

        _ext_lbl_timer_desc = QLabel("  └─ 활성화시 필드사냥을 하다가 세팅된 타이머에 맞춰 외부 보스 진행")
        _ext_lbl_timer_desc.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        _ext_lay.addWidget(_ext_lbl_timer_desc)

        # 보스 우선 토벌
        self._chk_ext_priority = QCheckBox("매크로 시작시 보스 우선 토벌")
        self._chk_ext_priority.setChecked(_cfg3.get("normal_hunt_ext_boss_priority", False))
        self._chk_ext_priority.setStyleSheet(f"color:{YELLOW}; font-weight:bold;")
        self._chk_ext_priority.stateChanged.connect(lambda s: (
            update_config("normal_hunt_ext_boss_priority", bool(s)),
            _update_zone_frames(),
        ))
        _ext_lay.addWidget(self._chk_ext_priority)

        _ext_lbl_priority_desc = QLabel("  └─ 활성화시 필드를 우선적으로 가지 않고 외부 보스부터 진행 후 필드사냥 진행")
        _ext_lbl_priority_desc.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        _ext_lay.addWidget(_ext_lbl_priority_desc)

        self._nh_ext_boss_sub.setVisible(_cfg3.get("normal_hunt_ext_boss_enabled", False))
        tab3_layout.addWidget(self._nh_ext_boss_sub)

        # 초기 로드 시 둘 다 체크된 경우 액션3 우선
        if self.chk_nh_action_3.isChecked() and self.chk_nh_action_4.isChecked():
            self.chk_nh_action_4.blockSignals(True)
            self.chk_nh_action_4.setChecked(False)
            self.chk_nh_action_4.blockSignals(False)
            update_config("normal_hunt_ext_boss_enabled", False)

        _nh_action_grp = QButtonGroup(tab3)
        _nh_action_grp.addButton(self.rb_nh_action_0, 0)
        _nh_action_grp.addButton(self.rb_nh_action_1, 1)
        _nh_action_grp.addButton(self.rb_nh_action_2, 2)
        _nh_action_grp.idClicked.connect(lambda i: (
            update_config("normal_hunt_action", i),
            _update_zone_frames(),
        ))
        self._update_nh_zone_frames = _update_zone_frames  # _update_nh_portals에서 재호출 가능하도록
        _update_zone_frames()  # 초기 로드 시 보스 상태 반영

        sep_nh3 = QFrame(); sep_nh3.setFrameShape(QFrame.HLine)
        sep_nh3.setStyleSheet(f"color:{DARK_BORDER};")
        tab3_layout.addWidget(sep_nh3)

        _nh_respawn_hint = (
            f"<b><span style='color:{RED}'>: 사냥터에서 </span>"
            f"<span style='color:{GREEN}'>사망시</span>"
            f"<span style='color:{RED}'> 세팅된 값에 따라 </span>"
            f"<span style='color:{GREEN}'>사냥터 복귀</span></b>"
        )
        self.chk_nh_respawn = QCheckBox("영웅 사망시 사냥터 복귀")
        self.chk_nh_respawn.setChecked(_cfg3.get("normal_hunt_respawn", True))
        self.chk_nh_respawn.stateChanged.connect(
            lambda s: (
                update_config("normal_hunt_respawn", bool(s)),
                _update_zone_frames(),
            )
        )
        _nh_respawn_row = QHBoxLayout()
        _nh_respawn_row.setSpacing(4)
        _nh_respawn_row.addWidget(self.chk_nh_respawn)
        self._nh_respawn_lbl = QLabel(_nh_respawn_hint)
        self._nh_respawn_lbl.setTextFormat(Qt.RichText)
        self._nh_respawn_lbl.setStyleSheet("background:transparent;")
        _nh_respawn_row.addWidget(self._nh_respawn_lbl)
        _nh_respawn_row.addStretch()
        tab3_layout.addLayout(_nh_respawn_row)

        def _build_logic_desc() -> str:
            cfg         = load_config()
            portal_name = self.combo_nh_portal_key.currentText()
            action      = _nh_action_grp.checkedId()
            pcfg        = next((p for p in PORTAL_CONFIGS if p.name == portal_name), None)

            # ── 구역 텍스트 ──
            if action == 0:
                zone_desc = "즉시 자동사냥"
            elif action == 1:
                if pcfg:
                    _zi       = cfg.get(f"{pcfg.cfg_prefix}_zone_idx", 0)
                    zone_desc = pcfg.zone_names[_zi] if _zi < len(pcfg.zone_names) else "?"
                else:
                    zone_desc = "구역 이동 사냥"
            else:
                zone_desc = "커스텀 좌표 사냥"

            # ── 색상 헬퍼 ──
            def _cp(t): return f"<span style='color:{ACCENT};font-weight:bold;'>{t}</span>"
            def _cz(t): return f"<span style='color:{YELLOW};font-weight:bold;'>{t}</span>"
            def _cb(t): return f"<span style='color:{RED};font-weight:bold;'>{t}</span>"
            def _cr(t): return f"<span style='color:#f38bab;font-weight:bold;'>{t}</span>"
            def _ct(t): return f"<span style='color:{ACCENT_H};font-weight:bold;'>{t}</span>"
            def _cg(t): return f"<span style='color:{GREEN};font-weight:bold;'>{t}</span>"
            def _cd(t): return f"<span style='color:{TEXT_DIM};'>{t}</span>"
            def _shdr(title):
                return (f"<span style='color:{ACCENT_H};font-size:13px;"
                        f"font-weight:bold;letter-spacing:1px;'>{title}</span>")
            def _row(label, val):
                return f"{_cd(label)}{ARR}{val}"

            ARR    = _cd(" → ")
            ARR_NL = "<br>" + _cd("→ ")
            BR     = "<br>"

            portal_h = _cp(portal_name)
            zone_h   = _cz(zone_desc)
            boss_on  = self.chk_nh_action_3.isChecked()
            ext_on   = self.chk_nh_action_4.isChecked()

            # ── 자동사냥 설정 ──
            auto_hunt   = self.chk_auto_hunt.isChecked()
            stay_hunt   = auto_hunt and self.chk_stay_hunt.isChecked()
            hunt_radius = self.spn_hunt_radius.value()

            # ── 보스 패널 데이터 수집 ──
            _bp = self._nh_boss_panels.get(portal_name) if pcfg else None
            _boss_order = cfg.get(f"{pcfg.cfg_prefix}_boss_order", []) if pcfg else []
            _checked_b = []
            if boss_on and _bp:
                _raw = [(k, _bp._boss_labels[k]) for k, chk in _bp._boss_chks if chk.isChecked()]
                _raw.sort(key=lambda x: _boss_order.index(x[0]) if x[0] in _boss_order else 999)
                _checked_b = _raw
            _t_on_b = (_bp._chk_boss_timer is not None and _bp._chk_boss_timer.isChecked()) if _bp else False
            try:    _t_sec_b = float(_bp._led_boss_timer.text()) if _bp else 60.0
            except: _t_sec_b = cfg.get(f"{pcfg.cfg_prefix}_boss_timer_sec", 60.0) if pcfg else 60.0
            _prio_b = cfg.get(f"{pcfg.cfg_prefix}_boss_priority",  False) if pcfg else False
            _nor_b  = cfg.get(f"{pcfg.cfg_prefix}_boss_no_return", False) if pcfg else False
            _boss_only = boss_on and bool(_checked_b) and not _t_on_b

            def _bh(rank_i, label):
                clean = label.replace("[BOSS]  ", "").replace("[BOSS] ", "").strip()
                return _cr(f"[{rank_i + 1}]") + " " + _cb(clean)

            boss_list_h = _cd(",  ").join(_bh(i, lbl) for i, (_, lbl) in enumerate(_checked_b))

            # ── 외부 보스 데이터 수집 ──
            _ext_rows = getattr(self, "_ext_boss_rows", []) if ext_on else []
            _ext_t_on = self._chk_ext_timer.isChecked() if ext_on else False
            try:    _ext_t_sec = float(self._led_ext_timer.text()) if ext_on else 60.0
            except: _ext_t_sec = cfg.get("normal_hunt_ext_boss_timer_sec", 60.0)
            _ext_prio = (self._chk_ext_priority.isChecked() and
                         self._chk_ext_priority.isEnabled()) if ext_on else False
            _ext_bl = [
                _cr(f"[{_i + 1}]") + " " + _cb(_r["boss_dd"].currentText())
                for _i, _r in enumerate(_ext_rows)
                if _r["boss_dd"].currentText() not in ("", "(선택)")
            ]
            _ext_boss_h = _cd(",  ").join(_ext_bl) if _ext_bl else _cd("(보스 미선택)")

            # ─────────────────────────────────────────────────────────
            # 섹션 1: 설정 요약
            # ─────────────────────────────────────────────────────────
            out = _shdr("[ 설정 요약 ]")
            out += BR + _row("포탈", portal_h)

            if auto_hunt:
                if stay_hunt:
                    out += BR + _row("자동사냥",
                        f"{_cg('ON')}  {_cd('|')}  {_cg('제자리 사냥')}"
                        f"  {_cd('반경:')} {_ct(str(hunt_radius))}")
                else:
                    out += BR + _row("자동사냥",
                        f"{_cg('ON')}  {_cd('|')}  {_cz('이동 사냥')}")
            else:
                out += BR + _row("자동사냥", _cd("OFF (수동)"))

            if not _boss_only:
                out += BR + _row("구역", zone_h)

            # ─────────────────────────────────────────────────────────
            # 섹션 2: 보스 설정
            # ─────────────────────────────────────────────────────────
            if boss_on and _checked_b:
                out += BR + BR + _shdr("[ 보스 설정 ]")
                out += BR + _row("보스", boss_list_h)
                if _t_on_b:
                    out += BR + _row("타이머", _ct(f"{_t_sec_b:.0f}초") + _cd(" 마다 보스 이동"))
                    out += BR + _row("우선토벌", _cg("ON") if _prio_b else _cd("OFF"))
                    out += BR + _row("복귀방식",
                        _cg("필드 경유 (마을 복귀 없음)") if _nor_b else _cd("마을 복귀"))
                else:
                    out += BR + _row("방식", _cd("보스만 반복 (타이머 없음)"))
            elif boss_on and not _checked_b:
                out += BR + _cd("※ 보스 미선택 — 사냥만 진행")

            # ─────────────────────────────────────────────────────────
            # 섹션 3: 외부 보스 설정
            # ─────────────────────────────────────────────────────────
            if ext_on:
                out += BR + BR + _shdr("[ 외부 보스 설정 ]")
                out += BR + _row("구역", zone_h)
                out += BR + _row("외부보스", _ext_boss_h)
                if _ext_t_on:
                    out += BR + _row("타이머", _ct(f"{_ext_t_sec:.0f}초") + _cd(" 마다 외부보스 이동"))
                    out += BR + _row("우선토벌", _cg("ON") if _ext_prio else _cd("OFF"))
                else:
                    out += BR + _row("방식", _cd("즉시 보스 이동 (타이머 없음)"))

            # ─────────────────────────────────────────────────────────
            # 섹션 4: 순환 흐름
            # ─────────────────────────────────────────────────────────
            out += BR + BR + _shdr("[ 순환 흐름 ]") + BR

            if ext_on:
                if not _ext_t_on:
                    flow = (f"{portal_h} 진입{ARR}{_ext_boss_h} {_cg('처치')}"
                            f"{ARR_NL}마을 복귀{ARR}{portal_h} 재진입{ARR}{_cg('반복')}")
                else:
                    _ep = []
                    if _ext_prio:
                        _ep.append(f"시작 즉시 외부 보스 이동{ARR}{_ext_boss_h} {_cg('처치')}")
                        _ep.append(f"{portal_h} 진입 후 {zone_h} 사냥")
                    else:
                        _ep.append(f"{portal_h} 진입 후 {zone_h} 사냥")
                    _ep.append(f"{_ct(f'{_ext_t_sec:.0f}초')} 후 외부 보스 이동{ARR}{_ext_boss_h} {_cg('처치')}")
                    _ep.append(f"마을 복귀{ARR}{portal_h} 재진입{ARR}{_cg('반복')}")
                    flow = ARR_NL.join(_ep)
            elif not boss_on or pcfg is None or pcfg.name not in self._nh_boss_panels:
                flow = f"{portal_h} 진입 후 {zone_h} 사냥만 진행 {_cd('(보스 없음)')}"
            elif not _checked_b:
                flow = f"{portal_h} 진입 후 {zone_h} 사냥만 진행 {_cd('(보스 미선택)')}"
            elif _boss_only:
                flow = (f"{portal_h} 진입{ARR}{boss_list_h} {_cg('처치')}"
                        f"{ARR_NL}마을 복귀{ARR}{portal_h} 재진입{ARR}{_cg('반복')}")
            else:
                _fp = []
                if _prio_b:
                    _fp.append(f"시작 즉시 보스 이동{ARR}{boss_list_h} {_cg('처치')}")
                    if _nor_b:
                        _fp.append(f"필드 경유로 {portal_h} {zone_h} {_cg('직접 복귀')} {_cd('(마을 복귀 없음)')}")
                    else:
                        _fp.append(f"마을 복귀{ARR}{portal_h} 진입 후 {zone_h} 사냥")
                else:
                    _fp.append(f"{portal_h} 진입 후 {zone_h} 사냥")
                _fp.append(f"{_ct(f'{_t_sec_b:.0f}초')} 후 보스 이동{ARR}{boss_list_h} {_cg('처치')}")
                if _nor_b:
                    _fp.append(
                        f"필드 경유로 {portal_h} {zone_h} {_cg('직접 복귀')} {_cd('(마을 복귀 없음)')}"
                        f"{ARR}{_cg('사냥 재개')}{ARR}{_cg('반복')}"
                    )
                else:
                    _fp.append(f"마을 복귀{ARR}{portal_h} 재진입{ARR}{_cg('반복')}")
                flow = ARR_NL.join(_fp)

            out += flow

            # ─────────────────────────────────────────────────────────
            # 섹션 5: 사망 처리
            # ─────────────────────────────────────────────────────────
            def _death_suffix() -> str:
                _respawn = self.chk_nh_respawn.isChecked()
                _br = "<br>"
                _pfx = "<b>**</b>"

                _hbf       = False
                _ds_only   = False
                _t_on      = False
                _t_sec     = 60.0

                if boss_on and pcfg is not None and pcfg.name in self._nh_boss_panels:
                    _p   = self._nh_boss_panels[pcfg.name]
                    _any = any(chk.isChecked() for _, chk in _p._boss_chks)
                    if _any:
                        _hbf    = True
                        _t_on   = _p._chk_boss_timer is not None and _p._chk_boss_timer.isChecked()
                        try:    _t_sec = float(_p._led_boss_timer.text())
                        except: _t_sec = cfg.get(f"{pcfg.cfg_prefix}_boss_timer_sec", 60.0)
                        _ds_only = not _t_on

                if ext_on and _ext_rows:
                    _hbf  = True
                    _t_on = _ext_t_on
                    _t_sec = _ext_t_sec

                def _next_action():
                    if _ds_only:
                        return f"{portal_h} 재진입{ARR}{_cg('보스 이동 재개')}"
                    if ext_on:
                        if _t_on:
                            return (f"{portal_h} 재진입{ARR}{zone_h} 사냥"
                                    f"{ARR}{_ct(f'{_t_sec:.0f}초')} 후 외부보스 이동")
                        return f"{portal_h} 재진입{ARR}{_cg('외부보스 이동')}"
                    if _hbf and _t_on:
                        return (f"{portal_h} 재진입{ARR}{zone_h} 사냥"
                                f"{ARR}{_ct(f'{_t_sec:.0f}초')} 후 보스 이동")
                    if _hbf:
                        return f"{portal_h} 재진입{ARR}{_cg('보스 이동 재개')}"
                    return f"{portal_h} 재진입{ARR}{zone_h} {_cg('사냥 재개')}"

                if _respawn:
                    _d1 = f"{_br}{_pfx} {portal_h} 사냥터 사망시{ARR}마을 복귀{ARR}{_next_action()}"
                else:
                    _d1 = (f"{_br}{_pfx} {portal_h} 사냥터 사망시{ARR}"
                           f"마을 복귀 후 {_cd('대기 (사냥터 복귀 안함)')}")

                _d2 = (
                    f"{_br}{_pfx} 보스 구역 사망시{ARR}마을 복귀{ARR}{_next_action()}"
                    if _hbf else ""
                )
                return _d1 + _d2

            out += BR + BR + _shdr("[ 사망 처리 ]") + _death_suffix()
            return out

        # 로직 설명 함수 저장 (사이드 패널에서 사용)
        self._build_logic_desc = _build_logic_desc

        self._logic_btns = []
        _btn_logic3 = QPushButton("Logic 설명")
        _btn_logic3.setFixedHeight(30)
        _btn_logic3.setCheckable(True)
        _btn_logic3.clicked.connect(self._toggle_logic_panel)
        self._logic_btns.append(_btn_logic3)
        tab3_layout.addWidget(_btn_logic3)
        tab3_layout.addStretch()
        self.tabs.addTab(tab3, "일반 사냥터")


    def _build_tab4(self):
        # ── Tab 4: 보스 레이드 ────────────────────────
        _cfg4 = load_config()
        tab4 = QWidget()
        tab4_layout = QVBoxLayout(tab4)
        tab4_layout.setSpacing(10)
        tab4_layout.setContentsMargins(16, 16, 16, 16)

        self.rb_boss_raid = QRadioButton("보스 레이드 활성화")
        self.rb_boss_raid.setChecked(_cfg4.get("boss_raid_enabled", False))
        self.rb_boss_raid.setEnabled(False)
        tab4_layout.addWidget(self.rb_boss_raid)

        sep_br = QFrame(); sep_br.setFrameShape(QFrame.HLine)
        sep_br.setStyleSheet(f"color:{DARK_BORDER};")
        tab4_layout.addWidget(sep_br)

        _PORTAL_KEYS = ["Q 포탈 | 라하린 숲", "W 포탈 | 아스탈 요새", "E 포탈 | 어둠얼음성채", "R 포탈 | 버려진 고성",
                        "A 포탈 | 바위협곡", "S 포탈 | 바람의 협곡", "D 포탈 | 시계태엽 공장", "F 포탈 | 속삭임의 숲",
                        "Z 포탈 | 이그니스영역", "X 포탈 | 정령계"]
        portal_row_br = QHBoxLayout()
        portal_row_br.addWidget(QLabel("포탈 진입:"))
        self.combo_br_portal_key = HotkeyDropdown(_PORTAL_KEYS)
        self.combo_br_portal_key.setFixedSize(200, 30)
        self.combo_br_portal_key.install_portal_align()
        _saved_br_key = _cfg4.get("boss_raid_portal_key", "Q 포탈 | 라하린 숲")
        self.combo_br_portal_key.setCurrentText(_saved_br_key)
        self.combo_br_portal_key.selectionChanged.connect(
            lambda t: update_config("boss_raid_portal_key", t)
        )
        portal_row_br.addWidget(self.combo_br_portal_key)
        portal_row_br.addStretch()
        tab4_layout.addLayout(portal_row_br)

        sep_br2 = QFrame(); sep_br2.setFrameShape(QFrame.HLine)
        sep_br2.setStyleSheet(f"color:{DARK_BORDER};")
        tab4_layout.addWidget(sep_br2)

        _br_saved_action = _cfg4.get("boss_raid_action", 0)

        self.rb_br_action_0 = QRadioButton("포탈 진입 후 즉시 해당 맵 자동사냥 진행")
        self.rb_br_action_1 = QRadioButton("포탈 진입 후 특정 구역으로 이동해서 자동사냥 진행")
        self.rb_br_action_2 = QRadioButton("포탈 진입 후 커스텀 좌표 이동해서 자동사냥 진행")

        [self.rb_br_action_0, self.rb_br_action_1,
         self.rb_br_action_2][_br_saved_action].setChecked(True)

        _br_hint_off = (f"<b><span style='color:{RED}'>: 제자리 사냥을 </span>"
                        f"<span style='color:{GREEN}'>OFF</span>"
                        f"<span style='color:{RED}'> 하는것을 추천</span></b>")
        _br_hint_on  = (f"<b><span style='color:{RED}'>: 제자리 사냥을 </span>"
                        f"<span style='color:{GREEN}'>ON</span>"
                        f"<span style='color:{RED}'> 하는것을 추천</span></b>")

        def _make_action_row_br(rb, hint_html=None):
            row = QHBoxLayout()
            row.setSpacing(4)
            row.addWidget(rb)
            if hint_html:
                lbl = QLabel(hint_html)
                lbl.setTextFormat(Qt.RichText)
                lbl.setStyleSheet("background:transparent;")
                row.addWidget(lbl)
            row.addStretch()
            return row

        tab4_layout.addLayout(_make_action_row_br(self.rb_br_action_0, _br_hint_off))
        tab4_layout.addLayout(_make_action_row_br(self.rb_br_action_1, _br_hint_on))
        tab4_layout.addLayout(_make_action_row_br(self.rb_br_action_2))

        self._br_custom_panel = _CustomCoordsPanel("br_custom_coords")
        self._br_custom_panel.setVisible(_br_saved_action == 2)
        tab4_layout.addWidget(self._br_custom_panel)

        # ── 보스 패널 (액션 무관, 포탈 키에 따라 표시) ─────────────────
        self._br_boss_panels: "dict[str, PortalBossPanel]" = {}
        for _pcfg in PORTAL_CONFIGS:
            if _pcfg.boss_defs:
                _bbp = PortalBossPanel(_pcfg)
                self._br_boss_panels[_pcfg.name] = _bbp
                _bbp.setVisible(_saved_br_key == _pcfg.name)
                tab4_layout.addWidget(_bbp)

        def _update_br_boss_panels():
            _key = self.combo_br_portal_key.currentText()
            for _pcfg in PORTAL_CONFIGS:
                if _pcfg.name in self._br_boss_panels:
                    self._br_boss_panels[_pcfg.name].setVisible(_key == _pcfg.name)

        self.combo_br_portal_key.selectionChanged.connect(lambda t: _update_br_boss_panels())

        _br_action_grp = QButtonGroup(tab4)
        _br_action_grp.addButton(self.rb_br_action_0, 0)
        _br_action_grp.addButton(self.rb_br_action_1, 1)
        _br_action_grp.addButton(self.rb_br_action_2, 2)
        _br_action_grp.idClicked.connect(lambda i: (
            update_config("boss_raid_action", i),
            self._br_custom_panel.setVisible(i == 2),
        ))

        sep_br3 = QFrame(); sep_br3.setFrameShape(QFrame.HLine)
        sep_br3.setStyleSheet(f"color:{DARK_BORDER};")
        tab4_layout.addWidget(sep_br3)

        _br_respawn_hint = (
            f"<b><span style='color:{RED}'>: 사냥터에서 </span>"
            f"<span style='color:{GREEN}'>사망시</span>"
            f"<span style='color:{RED}'> 세팅된 값에 따라 </span>"
            f"<span style='color:{GREEN}'>사냥터 복귀</span></b>"
        )
        self.chk_br_respawn = QCheckBox("영웅 사망시 사냥터 복귀")
        self.chk_br_respawn.stateChanged.connect(
            lambda s: update_config("boss_raid_respawn", bool(s))
        )
        self.chk_br_respawn.setChecked(_cfg4.get("boss_raid_respawn", True))
        if "boss_raid_respawn" not in _cfg4:
            update_config("boss_raid_respawn", True)
        _br_respawn_row = QHBoxLayout()
        _br_respawn_row.setSpacing(4)
        _br_respawn_row.addWidget(self.chk_br_respawn)
        _br_respawn_lbl = QLabel(_br_respawn_hint)
        _br_respawn_lbl.setTextFormat(Qt.RichText)
        _br_respawn_lbl.setStyleSheet("background:transparent;")
        _br_respawn_row.addWidget(_br_respawn_lbl)
        _br_respawn_row.addStretch()
        tab4_layout.addLayout(_br_respawn_row)

        _btn_logic4 = QPushButton("Logic 설명")
        _btn_logic4.setFixedHeight(30)
        _btn_logic4.setCheckable(True)
        _btn_logic4.clicked.connect(self._toggle_logic_panel)
        self._logic_btns.append(_btn_logic4)
        tab4_layout.addWidget(_btn_logic4)
        tab4_layout.addStretch()
        self.tabs.addTab(tab4, "보스 레이드")

        # 일반 사냥터 ↔ 보스 레이드 상호 배타 그룹
        self.bg_hunt_mode = QButtonGroup(self)
        self.bg_hunt_mode.setExclusive(True)
        self.bg_hunt_mode.addButton(self.rb_normal_hunt)
        self.bg_hunt_mode.addButton(self.rb_boss_raid)

        def _update_nh_portals(enabled: bool):
            self.combo_nh_portal_key.setEnabled(enabled)
            self.rb_nh_action_0.setEnabled(enabled)
            self.rb_nh_action_1.setEnabled(enabled)
            self.rb_nh_action_2.setEnabled(enabled)
            self.chk_nh_action_3.setEnabled(enabled)
            for _pw in self._portal_widgets.values():
                _pw.setEnabled(enabled)
            self._nh_custom_panel.setEnabled(enabled)
            for _bp in self._nh_boss_panels.values():
                _bp.setEnabled(enabled)
            self.chk_nh_respawn.setEnabled(enabled)
            self._nh_respawn_lbl.setEnabled(enabled)
            update_config("normal_hunt_enabled", enabled)
            if enabled:
                for _bp in self._nh_boss_panels.values():
                    _bp.sync_ui()
                self._update_nh_zone_frames()  # 보스 패널 표시 상태 재적용

        def _update_br_portals(enabled: bool):
            self.combo_br_portal_key.setEnabled(enabled)
            self.rb_br_action_0.setEnabled(enabled)
            self.rb_br_action_1.setEnabled(enabled)
            self.rb_br_action_2.setEnabled(enabled)
            self._br_custom_panel.setEnabled(enabled)
            for _bbp in self._br_boss_panels.values():
                _bbp.setEnabled(enabled)
            self.chk_br_respawn.setEnabled(enabled)
            _br_respawn_lbl.setEnabled(enabled)
            update_config("boss_raid_enabled", enabled)
            if enabled:
                for _bbp in self._br_boss_panels.values():
                    _bbp.sync_ui()

        _update_nh_portals(self.rb_normal_hunt.isChecked())
        _update_br_portals(self.rb_boss_raid.isChecked())
        self.rb_normal_hunt.toggled.connect(_update_nh_portals)
        self.rb_boss_raid.toggled.connect(_update_br_portals)


    def _build_tab567(self):
        _cfg = load_config()
        # ── Tab 5: 빈 탭 ────────────────────────────
        self.tabs.addTab(QWidget(), "탭 5")

        # ── Tab 6: 녹스 맵 자동 다운로드 ─────────────
        tab6 = QWidget()
        tab6_layout = QVBoxLayout(tab6)
        tab6_layout.setContentsMargins(16, 16, 16, 16)
        tab6_layout.setSpacing(10)

        lbl_nox_title = QLabel("녹스 맵 자동 다운로드")
        lbl_nox_title.setStyleSheet("font-size:15px; font-weight:bold;")
        tab6_layout.addWidget(lbl_nox_title)

        self.chk_nox_enabled = ConfigCheckBox("nox_map_enabled", "기능 활성화", True)
        self.chk_nox_enabled.toggled.connect(self._on_nox_enabled_toggled)
        tab6_layout.addWidget(self.chk_nox_enabled)

        sep_nox = QFrame(); sep_nox.setFrameShape(QFrame.HLine)
        sep_nox.setStyleSheet(f"color:{DARK_BORDER};")
        tab6_layout.addWidget(sep_nox)

        # URL 행
        r_nox_url = QHBoxLayout()
        lbl_nox_url = QLabel("녹스 맵 다운로드 URL:")
        lbl_nox_url.setFixedWidth(170)
        r_nox_url.addWidget(lbl_nox_url)
        self.edit_nox_url = QLineEdit(
            _cfg.get("nox_map_url", "https://m16tool.xyz/Game/NOXRE/Download/Index"))
        self.edit_nox_url.editingFinished.connect(self._save_nox_url)
        r_nox_url.addWidget(self.edit_nox_url)
        tab6_layout.addLayout(r_nox_url)

        # 경로 행 (읽기 전용 표시)
        r_nox_path = QHBoxLayout()
        lbl_nox_path_title = QLabel("녹스 맵 다운로드 경로:")
        lbl_nox_path_title.setFixedWidth(170)
        r_nox_path.addWidget(lbl_nox_path_title)
        _nox_display_path = os.path.expandvars(r"%userprofile%\Documents\Warcraft III\Maps")
        lbl_nox_path_val = QLabel(_nox_display_path)
        lbl_nox_path_val.setStyleSheet(f"color:{TEXT_DIM};")
        r_nox_path.addWidget(lbl_nox_path_val)
        tab6_layout.addLayout(r_nox_path)

        sep_nox2 = QFrame(); sep_nox2.setFrameShape(QFrame.HLine)
        sep_nox2.setStyleSheet(f"color:{DARK_BORDER};")
        tab6_layout.addWidget(sep_nox2)

        # 상태 + 수동 확인 버튼
        r_nox_ctrl = QHBoxLayout()
        self.lbl_nox_status = QLabel("대기 중")
        self.lbl_nox_status.setStyleSheet(f"color:{TEXT_DIM};")
        r_nox_ctrl.addWidget(self.lbl_nox_status)
        r_nox_ctrl.addStretch()
        self.btn_nox_check = QPushButton("지금 확인")
        self.btn_nox_check.setFixedHeight(28)
        self.btn_nox_check.clicked.connect(self._nox_check_now)
        r_nox_ctrl.addWidget(self.btn_nox_check)
        tab6_layout.addLayout(r_nox_ctrl)

        # 로그 영역
        self.log_nox = QTextEdit()
        self.log_nox.setReadOnly(True)
        tab6_layout.addWidget(self.log_nox)

        self.tabs.addTab(tab6, "녹스 맵 자동 다운로드")

        # ── Tab 7: 관리자 전용 ────────────────────────
        tab7 = QWidget()
        tab7_layout = QVBoxLayout(tab7)
        tab7_layout.setContentsMargins(16, 16, 16, 16)
        tab7_layout.setSpacing(12)

        # 체크박스 + 상태
        row_admin = QHBoxLayout()
        self.chk_admin = QCheckBox("Admin Mode")
        self.chk_admin.toggled.connect(self._on_admin_toggled)
        self.lbl_admin_status = QLabel("OFF")
        self.lbl_admin_status.setFont(QFont("Consolas", 11, QFont.Bold))
        self.lbl_admin_status.setStyleSheet(f"color:{RED};")
        row_admin.addWidget(self.chk_admin)
        row_admin.addSpacing(12)
        row_admin.addWidget(QLabel("Status:"))
        row_admin.addWidget(self.lbl_admin_status)
        row_admin.addStretch()
        tab7_layout.addLayout(row_admin)

        sep7 = QFrame(); sep7.setFrameShape(QFrame.HLine)
        sep7.setStyleSheet(f"color:{DARK_BORDER};")
        tab7_layout.addWidget(sep7)

        # 좌표 / RGB 표시 (타이틀 폭 통일)
        _ADMIN_LBL_W = 200

        def make_admin_row(label_text, val_width):
            h = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setFixedWidth(_ADMIN_LBL_W)
            lbl.setStyleSheet(f"color:{TEXT_DIM};")
            val = QLabel("—")
            val.setFont(QFont("Consolas", 11))
            val.setFixedWidth(val_width)
            val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            h.addWidget(lbl)
            h.addWidget(val)
            h.addStretch()
            tab7_layout.addLayout(h)
            return val

        # X: -999   Y: -999 → 최대 약 160px
        self.lbl_admin_coord = make_admin_row("Client Coordinate:", 220)

        # RGB 행 (단일 라벨 + B값 바로 뒤 스와치)
        h_rgb = QHBoxLayout()
        lbl_rgb_title = QLabel("Client Coordinate RGB:")
        lbl_rgb_title.setFixedWidth(_ADMIN_LBL_W)
        lbl_rgb_title.setStyleSheet(f"color:{TEXT_DIM};")
        self.lbl_admin_rgb = QLabel("—")
        self.lbl_admin_rgb.setFont(QFont("Consolas", 11))
        # R: 255   G: 255   B: 255 → 최대 약 190px
        self.lbl_admin_rgb.setFixedWidth(190)
        self.lbl_admin_rgb.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lbl_admin_rgb.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_admin_swatch = QLabel()
        self.lbl_admin_swatch.setFixedSize(22, 22)
        self.lbl_admin_swatch.setStyleSheet(
            f"background:{DARK_BORDER}; border:1px solid {TEXT_DIM}; border-radius:4px;"
        )

        h_rgb.addWidget(lbl_rgb_title)
        h_rgb.addWidget(self.lbl_admin_rgb)
        h_rgb.addSpacing(10)
        h_rgb.addWidget(self.lbl_admin_swatch)
        h_rgb.addStretch()
        tab7_layout.addLayout(h_rgb)

        # 마지막 캡처 필드
        self.lbl_last_capture = QLabel("—")
        self.lbl_last_capture.setFont(QFont("Consolas", 10))
        self.lbl_last_capture.setStyleSheet(
            f"color:{TEXT_DIM}; background:{DARK_PANEL};"
            f" border:1px solid {DARK_BORDER}; border-radius:4px; padding:4px 8px;"
        )
        self.lbl_last_capture.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tab7_layout.addWidget(self.lbl_last_capture)

        _CHK_W = 140  # Capture / Image 핫키 체크박스 가로폭 통일

        # Capture Hotkey 행
        h_cap = QHBoxLayout()
        self.chk_capture = QCheckBox("Capture Hotkey:")
        self.chk_capture.setFixedWidth(_CHK_W)
        self.chk_capture.setChecked(True)
        self.chk_capture.setEnabled(False)
        self.chk_capture.toggled.connect(self._on_capture_hotkey_toggled)
        self.dd_capture_key = HotkeyDropdown(_ALL_KEYS)
        self.dd_capture_key.setFixedSize(160, 30)
        self.dd_capture_key.setCurrentText("F10")
        self.dd_capture_key.setEnabled(False)
        self.dd_capture_key.selectionChanged.connect(self._on_capture_key_changed)
        h_cap.addWidget(self.chk_capture)
        h_cap.addSpacing(8)
        h_cap.addWidget(self.dd_capture_key)
        h_cap.addStretch()
        tab7_layout.addLayout(h_cap)

        sep_save = QFrame(); sep_save.setFrameShape(QFrame.HLine)
        sep_save.setStyleSheet(f"color:{DARK_BORDER};")
        tab7_layout.addWidget(sep_save)

        # Image Hotkey 행
        h_save = QHBoxLayout()
        self.chk_save = QCheckBox("Image Hotkey:")
        self.chk_save.setFixedWidth(_CHK_W)
        self.chk_save.setChecked(True)
        self.chk_save.setEnabled(False)
        self.chk_save.toggled.connect(self._on_save_hotkey_toggled)
        self.dd_save_key = HotkeyDropdown(_ALL_KEYS)
        self.dd_save_key.setFixedSize(160, 30)
        self.dd_save_key.setCurrentText("F11")
        self.dd_save_key.setEnabled(False)
        self.dd_save_key.selectionChanged.connect(self._on_save_key_changed)
        h_save.addWidget(self.chk_save)
        h_save.addSpacing(8)
        h_save.addWidget(self.dd_save_key)
        h_save.addStretch()
        tab7_layout.addLayout(h_save)

        # 파일명 + 저장/취소 버튼
        h_fname = QHBoxLayout()
        h_fname.addWidget(QLabel("파일명:"))
        self.edit_save_name = QLineEdit()
        self.edit_save_name.setPlaceholderText("파일명 입력 (.png 자동)")
        self.edit_save_name.setEnabled(False)
        h_fname.addWidget(self.edit_save_name)
        self.btn_save_img = QPushButton("저장")
        self.btn_save_img.setFixedWidth(70)
        self.btn_save_img.setEnabled(False)
        self.btn_save_img.clicked.connect(self._save_snapshot_to_file)
        self.btn_cancel_snap = QPushButton("취소")
        self.btn_cancel_snap.setFixedWidth(60)
        self.btn_cancel_snap.setEnabled(False)
        self.btn_cancel_snap.clicked.connect(self._unfreeze_admin)
        h_fname.addWidget(self.btn_save_img)
        h_fname.addWidget(self.btn_cancel_snap)
        tab7_layout.addLayout(h_fname)

        # 스냅샷 프리뷰
        self.lbl_snapshot = QLabel("스냅샷 없음")
        self.lbl_snapshot.setAlignment(Qt.AlignCenter)
        self.lbl_snapshot.setMinimumHeight(120)
        self.lbl_snapshot.setStyleSheet(
            f"background:{DARK_PANEL}; border:1px solid {DARK_BORDER};"
            f" border-radius:6px; color:{TEXT_DIM};"
        )
        tab7_layout.addWidget(self.lbl_snapshot)

        # 저장 상태 라벨
        self.lbl_save_status = QLabel("")
        self.lbl_save_status.setFont(QFont("Consolas", 10))
        self.lbl_save_status.setStyleSheet(f"color:{TEXT_DIM};")
        tab7_layout.addWidget(self.lbl_save_status)

        # ── OCR 구분선 ──────────────────────────────
        sep_ocr = QFrame(); sep_ocr.setFrameShape(QFrame.HLine)
        sep_ocr.setStyleSheet(f"color:{DARK_BORDER};")
        tab7_layout.addWidget(sep_ocr)

        lbl_ocr_title = QLabel("OCR 감지")
        lbl_ocr_title.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        tab7_layout.addWidget(lbl_ocr_title)

        # 영역 지정 행
        row_ocr_region = QHBoxLayout()
        self.btn_ocr_region = QPushButton("영역 지정")
        self.btn_ocr_region.setFixedHeight(28)
        self.btn_ocr_region.clicked.connect(self._start_ocr_select)
        row_ocr_region.addWidget(self.btn_ocr_region)
        row_ocr_region.addSpacing(8)
        self.lbl_ocr_region = QLabel("미지정")
        self.lbl_ocr_region.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        self.lbl_ocr_region.setWordWrap(True)
        row_ocr_region.addWidget(self.lbl_ocr_region, stretch=1)
        tab7_layout.addLayout(row_ocr_region)

        # 인식 모드 행
        row_ocr_mode = QHBoxLayout()
        row_ocr_mode.addWidget(QLabel("인식 모드"))
        self.cmb_ocr_mode = QComboBox()
        self.cmb_ocr_mode.addItem("한글")
        self.cmb_ocr_mode.addItem("한글+숫자")
        self.cmb_ocr_mode.setFixedWidth(120)
        self.cmb_ocr_mode.setFixedHeight(28)
        row_ocr_mode.addWidget(self.cmb_ocr_mode)
        row_ocr_mode.addStretch()
        if not _kor_available():
            self.cmb_ocr_mode.model().item(0).setEnabled(False)
            self.cmb_ocr_mode.model().item(1).setEnabled(False)
            lbl_kor = QLabel("kor.traineddata 없음")
            lbl_kor.setStyleSheet(f"color:{RED}; font-size:10px;")
            row_ocr_mode.addWidget(lbl_kor)
        tab7_layout.addLayout(row_ocr_mode)

        # 감지 결과
        self.lbl_ocr_result = QLabel("—")
        self.lbl_ocr_result.setFont(QFont("Malgun Gothic", 13, QFont.Bold))
        self.lbl_ocr_result.setAlignment(Qt.AlignCenter)
        self.lbl_ocr_result.setWordWrap(True)
        self.lbl_ocr_result.setMinimumHeight(48)
        self.lbl_ocr_result.setStyleSheet(
            f"background:{DARK_PANEL}; color:{ACCENT};"
            f" border:1px solid {DARK_BORDER}; border-radius:6px; padding:6px;"
        )
        tab7_layout.addWidget(self.lbl_ocr_result)

        # 실시간 + 갱신 간격
        row_ocr_ctrl = QHBoxLayout()
        self.btn_ocr_toggle = QPushButton("▶ 실시간")
        self.btn_ocr_toggle.setCheckable(True)
        self.btn_ocr_toggle.setFixedWidth(90)
        self.btn_ocr_toggle.setFixedHeight(28)
        self.btn_ocr_toggle.clicked.connect(self._toggle_ocr_realtime)
        row_ocr_ctrl.addWidget(self.btn_ocr_toggle)
        row_ocr_ctrl.addSpacing(10)
        row_ocr_ctrl.addWidget(QLabel("갱신 간격"))
        self.spn_ocr_interval = QSpinBox()
        self.spn_ocr_interval.setRange(100, 5000)
        self.spn_ocr_interval.setSingleStep(100)
        self.spn_ocr_interval.setValue(500)
        self.spn_ocr_interval.setSuffix(" ms")
        self.spn_ocr_interval.setFixedWidth(90)
        self.spn_ocr_interval.setFixedHeight(28)
        self.spn_ocr_interval.valueChanged.connect(
            lambda v: self._ocr_timer.setInterval(v) if self._ocr_timer.isActive() else None
        )
        row_ocr_ctrl.addWidget(self.spn_ocr_interval)
        row_ocr_ctrl.addStretch()
        tab7_layout.addLayout(row_ocr_ctrl)

        tab7_layout.addStretch()
        self.tabs.addTab(tab7, "관리자 전용")

    def _apply_theme(self):
        _assets = _resource_path("assets").replace("\\", "/")
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {DARK_BG};
                color: {TEXT};
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }}
            QLabel {{ background: transparent; }}
            QLineEdit {{
                background-color: {DARK_BG};
                border: 1px solid {DARK_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                color: {TEXT};
            }}
            QLineEdit:disabled {{
                background-color: {DARK_PANEL};
                border: 1px solid {DARK_BORDER};
                color: {TEXT_DIM};
            }}
            QCheckBox {{
                color: {TEXT};
                font-size: 13px;
                font-weight: bold;
                spacing: 8px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                image: url("{_assets}/check_off.svg");
            }}
            QCheckBox::indicator:checked {{
                image: url("{_assets}/check_on.svg");
            }}
            QCheckBox::indicator:checked:hover {{
                image: url("{_assets}/check_on_hover.svg");
            }}
            QCheckBox::indicator:hover {{
                image: url("{_assets}/check_hover.svg");
            }}
            QCheckBox::indicator:disabled {{
                image: url("{_assets}/check_disabled.svg");
            }}
            QCheckBox::indicator:checked:disabled {{
                image: url("{_assets}/check_on_disabled.svg");
            }}
            QCheckBox:disabled {{
                color: {TEXT_DIM};
            }}
            QRadioButton {{
                background: transparent;
                color: {TEXT};
                font-size: 13px;
                font-weight: bold;
                spacing: 8px;
            }}
            QRadioButton::indicator {{
                width: 16px;
                height: 16px;
                image: url("{_assets}/radio_off.svg");
            }}
            QRadioButton::indicator:checked {{
                image: url("{_assets}/radio_on.svg");
            }}
            QRadioButton::indicator:checked:hover {{
                image: url("{_assets}/radio_on_hover.svg");
            }}
            QRadioButton::indicator:hover {{
                image: url("{_assets}/radio_hover.svg");
            }}
            QRadioButton::indicator:disabled {{
                image: url("{_assets}/radio_disabled.svg");
            }}
            QRadioButton::indicator:checked:disabled {{
                image: url("{_assets}/radio_on_disabled.svg");
            }}
            QRadioButton:disabled {{
                color: {TEXT_DIM};
            }}
            QPushButton {{
                background-color: {ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {ACCENT_H}; }}
            QPushButton:disabled {{
                background-color: {DARK_BORDER};
                color: {TEXT_DIM};
            }}
            QTextEdit {{
                background-color: {DARK_BG};
                border: 1px solid {DARK_BORDER};
                border-radius: 4px;
                color: {TEXT};
            }}
            QScrollBar:vertical {{
                background: {DARK_BG}; width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: {DARK_BORDER};
                border-radius: 4px;
                min-height: 20px;
            }}
            QTabWidget::pane {{
                border: 1px solid {DARK_BORDER};
                border-radius: 4px;
                background: {DARK_PANEL};
                padding: 6px;
            }}
            QTabBar::tab {{
                background: {DARK_BG};
                color: {TEXT_DIM};
                border: 1px solid {DARK_BORDER};
                border-bottom: none;
                border-radius: 4px 4px 0 0;
                padding: 5px 14px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {DARK_PANEL};
                color: {TEXT};
                border-bottom: 1px solid {DARK_PANEL};
            }}
            QTabBar::tab:hover:!selected {{
                color: {ACCENT_H};
                border-color: {ACCENT};
            }}
        """)

    # ── 슬롯 ──────────────────────────────────────
    def _browse(self):
        path = QFileDialog.getExistingDirectory(
            self, "JNLoader 폴더 선택", self.edit_path.text() or ""
        )
        if path:
            self.edit_path.setText(path)
            self._save_path()

    def _save_path(self):
        update_config("jnloader_path", self.edit_path.text())

    def _on_wmode_changed(self, checked: bool):
        if not checked:
            return
        mode = "fullscreen" if self.rb_fullscreen.isChecked() else "windowed"
        update_config("wc3_window_mode", mode)

    def _save_room_name(self):
        update_config("room_name", self.edit_room.text().strip())

    def _save_password(self):
        update_config("bnet_password", encrypt_password(self.edit_pw.text()))

    def _toggle_pw(self, checked: bool):
        self.edit_pw.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)


    def _append_log(self, msg: str, level: str = "info"):
        colors = {"info": TEXT, "success": GREEN, "warn": YELLOW, "error": RED}
        color  = colors.get(level, TEXT)
        sb = self.log_edit.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        # append() 는 항상 맨 아래로 스크롤하므로 커서 삽입 방식 사용
        scroll_val = sb.value()
        cursor = self.log_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(f'<span style="color:{color};">{msg}</span><br>')
        if at_bottom:
            self.log_edit.moveCursor(QTextCursor.End)
        else:
            sb.setValue(scroll_val)

    def _update_last_log(self, msg: str, level: str = "info"):
        """마지막 줄 텍스트만 덮어씀 (게이지 갱신용). 블록 구분자는 건드리지 않음."""
        colors = {"info": TEXT, "success": GREEN, "warn": YELLOW, "error": RED}
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors.get(level, TEXT)))
        sb = self.log_edit.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        scroll_val = sb.value()
        cursor = self.log_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(msg, fmt)
        if at_bottom:
            self.log_edit.moveCursor(QTextCursor.End)
        else:
            sb.setValue(scroll_val)

    def _update_status(self, text: str, color: str = TEXT):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(
            f"color:{color}; font-size:12px; padding-left:10px;"
        )

    def _on_role_changed(self, _=None):
        is_host      = self.rb_host.isChecked()
        is_freematch = self.rb_freematch.isChecked()
        self.tog_private.setEnabled(is_host)
        self.tog_auto.setEnabled(is_host)
        auto_on = is_host and self.tog_auto.isChecked()
        self.spn_count.setEnabled(auto_on)
        self.spn_as_timeout.setEnabled(auto_on)
        self.spn_dr.setEnabled(is_host)
        dim = TEXT_DIM if not is_host else TEXT
        for lbl in (self.lbl_priv, self.lbl_auto, self.lbl_dr, self.lbl_as_timeout):
            lbl.setStyleSheet(f"color:{dim};")
        self._fm_panel.setVisible(is_freematch)
        self.edit_room.setEnabled(not is_freematch)
        self.lbl_room.setEnabled(not is_freematch)
        self.lbl_room.setStyleSheet(f"color:{TEXT_DIM};" if is_freematch else "")
        role = "host" if is_host else ("freematch" if is_freematch else "guest")
        update_config("role", role)

    def _on_dr_changed(self, val: int):
        update_config("dr_delay", val)
        # 게임이 켜져 있으면 실시간 적용
        ok, msg = write_game_delay(val)
        if ok:
            self._append_log(f"[{now()}] {msg}", "success")
        # 실패(게임 꺼져있음 등)는 조용히 무시



    def _on_auto_save_interval_changed(self):
        update_config("auto_save_interval", self.spn_auto_save.value())

    def _on_smart_key_toggled(self, on: bool):
        if on:
            hero_vk = ord(str(self.spn_hero_group.value()))
            _smart_hook.start(hero_vk)
        else:
            _smart_hook.stop()

    def _on_chat_cmd_changed(self):
        update_config_multi({
            "cmd_suicide_enabled": self.chk_cmd_suicide.isChecked(),
            "cmd_suicide_key":     self.dd_cmd_suicide.currentText(),
            "cmd_save_enabled":    self.chk_cmd_save.isChecked(),
            "cmd_save_key":        self.dd_cmd_save.currentText(),
            "cmd_effect_enabled":  self.chk_cmd_effect.isChecked(),
            "cmd_effect_key":      self.dd_cmd_effect.currentText(),
        })
        cmds: dict = {}
        for enabled, key_name, text in [
            (self.chk_cmd_suicide.isChecked(), self.dd_cmd_suicide.currentText(), "-suicide"),
            (self.chk_cmd_save.isChecked(),    self.dd_cmd_save.currentText(),    "-save"),
            (self.chk_cmd_effect.isChecked(),  self.dd_cmd_effect.currentText(),  "-이펙트"),
        ]:
            if enabled:
                vk = _KEY_NAME_TO_VK.get(key_name)
                if vk:
                    cmds[vk] = text
        _smart_hook.update_chat_cmds(cmds)

    def _on_exit_cmd_changed(self):
        update_config_multi({
            "cmd_exit_enabled": self.chk_cmd_exit.isChecked(),
            "cmd_exit_key":     self.dd_cmd_exit.currentText(),
        })
        vk = _KEY_NAME_TO_VK.get(self.dd_cmd_exit.currentText(), 0) if self.chk_cmd_exit.isChecked() else 0
        _smart_hook.update_exit_cmd(vk)

    # ── 녹스 맵 자동 다운로드 ────────────────────────
    def _on_nox_enabled_toggled(self, on: bool):
        if on:
            self._nox_check_now()
            self._nox_timer.start()
        else:
            self._nox_timer.stop()

    def _save_nox_url(self):
        update_config("nox_map_url", self.edit_nox_url.text().strip())

    def _nox_append_log(self, msg: str, level: str = "info"):
        colors = {"info": TEXT, "success": GREEN, "warn": YELLOW, "error": RED}
        color  = colors.get(level, TEXT)
        sb = self.log_nox.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        self.log_nox.append(f'<span style="color:{color};">[{now()}] {msg}</span>')
        if at_bottom:
            self.log_nox.moveCursor(QTextCursor.End)

    def _nox_update_last_log(self, msg: str, level: str = "info"):
        colors = {"info": TEXT, "success": GREEN, "warn": YELLOW, "error": RED}
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors.get(level, TEXT)))
        cursor = self.log_nox.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(f"[{now()}] {msg}", fmt)
        self.log_nox.moveCursor(QTextCursor.End)

    def _nox_set_status(self, msg: str, color: str = TEXT):
        self.lbl_nox_status.setText(msg)
        self.lbl_nox_status.setStyleSheet(f"color:{color};")

    def _nox_check_now(self):
        if self._nox_checking:
            return
        self._nox_checking = True
        self.btn_nox_check.setEnabled(False)
        threading.Thread(target=self._nox_run_check, daemon=True).start()

    def _nox_run_check(self):
        sig = self._nox_signals
        try:
            import requests as _req
            import re as _re
            _CDN_BASE = "https://cdn.m16tool.xyz/"
            _SAVE_DIR = os.path.expandvars(
                r"%userprofile%\Documents\Warcraft III\Maps")
            _HEADERS  = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/122.0.0.0 Safari/537.36"
            }
            url = load_config().get(
                "nox_map_url", "https://m16tool.xyz/Game/NOXRE/Download/Index")

            sig.status_sig.emit("확인 중...", YELLOW)
            sig.log_sig.emit("버전 체크 중...", "info")

            try:
                resp = _req.get(url, headers=_HEADERS, timeout=15)
                resp.raise_for_status()
            except Exception as e:
                sig.log_sig.emit(f"[오류] 페이지 요청 실패: {e}", "error")
                sig.status_sig.emit("오류", RED)
                return

            m = _re.search(
                r'(NOX\s*RPG\s*[^"\'<>\r\n]+?\.w3x)', resp.text, _re.IGNORECASE)
            if not m:
                sig.log_sig.emit("[경고] 파일명을 찾지 못했습니다. URL을 확인해주세요.", "warn")
                sig.status_sig.emit("파싱 실패", RED)
                return

            filename  = m.group(1).strip()
            save_path = os.path.join(_SAVE_DIR, filename)
            sig.log_sig.emit(f"최신 파일명: {filename}", "info")

            if os.path.exists(save_path):
                sig.log_sig.emit("변경사항 없음 (최신 버전)", "success")
                sig.status_sig.emit("최신 버전", GREEN)
                return

            sig.log_sig.emit(f"새 버전 감지 → 다운로드 시작", "warn")
            sig.status_sig.emit("다운로드 중...", YELLOW)
            os.makedirs(_SAVE_DIR, exist_ok=True)
            dl_url = _CDN_BASE + _req.utils.quote(filename, safe="")
            try:
                downloaded = 0
                with _req.get(dl_url, headers=_HEADERS, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("content-length", 0))
                    with open(save_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                pct = downloaded / total * 100
                                sig.update_sig.emit(
                                    f"다운로드 중... {pct:.1f}%  ({downloaded//1024} KB)", "info")
                sig.log_sig.emit(
                    f"다운로드 완료: {filename}  ({downloaded//1024} KB)", "success")
                sig.status_sig.emit("다운로드 완료", GREEN)
            except Exception as e:
                sig.log_sig.emit(f"[오류] 다운로드 실패: {e}", "error")
                sig.status_sig.emit("다운로드 실패", RED)
                if os.path.exists(save_path):
                    os.remove(save_path)

        except ImportError:
            sig.log_sig.emit("[오류] requests 라이브러리가 설치되어 있지 않습니다.", "error")
            sig.status_sig.emit("오류", RED)
        finally:
            self._nox_checking = False
            QTimer.singleShot(0, lambda: self.btn_nox_check.setEnabled(True))

    def _on_private_toggled(self, on: bool):
        update_config("room_private", on)

    def _on_auto_toggled(self, on: bool):
        host = self.rb_host.isChecked()
        self.spn_count.setEnabled(on and host)
        self.spn_as_timeout.setEnabled(on and host)
        update_config("auto_start", on)


    def _on_as_timeout_changed(self, val: int):
        update_config("auto_start_timeout", val)

    def _on_character_changed(self, btn):
        update_config("character", btn.text())

    def _on_hero_group_changed(self, val: int):
        if val == self.spn_storage_group.value():
            QMessageBox.warning(self, "부대지정 중복",
                f"영웅과 창고의 부대 번호가 같을 수 없습니다. ({val}번)")
            return
        update_config("hero_group", val)
        _smart_hook._hero_vk = ord(str(val))

    def _on_storage_group_changed(self, val: int):
        if val == self.spn_hero_group.value():
            QMessageBox.warning(self, "부대지정 중복",
                f"영웅과 창고의 부대 번호가 같을 수 없습니다. ({val}번)")
            return
        update_config("storage_group", val)


    def _launch_jnloader(self):
        jn_dir = self.edit_path.text().strip()
        if not jn_dir:
            self._append_log(f"[{now()}] [오류] JNLoader 폴더가 설정되지 않았습니다.", "error")
            return False
        jn_exe = os.path.join(jn_dir, "JNLoader.exe")
        if not os.path.isfile(jn_exe):
            self._append_log(f"[{now()}] [오류] JNLoader.exe 를 찾을 수 없습니다: {jn_exe}", "error")
            return False

        mon_w = ctypes.windll.user32.GetSystemMetrics(0)
        mon_h = ctypes.windll.user32.GetSystemMetrics(1)
        is_fhd = (mon_w == 1920 and mon_h == 1080)
        self._append_log(f"[{now()}] 모니터 해상도: {mon_w} × {mon_h}", "info")

        ok, msg = patch_war3_preferences(is_fhd)
        self._append_log(f"[{now()}] {msg}", "success" if ok else "warn")

        ok2, msg2 = patch_war3_resolution_registry()
        self._append_log(f"[{now()}] {msg2}", "success" if ok2 else "warn")

        # 창모드 선택 시에만 -window 인자 전달
        cfg2 = load_config()
        use_window = (not is_fhd) and (cfg2.get("wc3_window_mode", "fullscreen") == "windowed")
        jn_args = "-window" if use_window else None

        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", jn_exe, jn_args, jn_dir, 1)
            self._append_log(f"[{now()}] JNLoader.exe 실행 완료", "success")
            return True
        except Exception as e:
            self._append_log(f"[{now()}] [오류] JNLoader 실행 실패: {e}", "error")
            return False

    # ── War3 프로세스 모니터 ──────────────────────────
    def _check_war3_alive(self):
        """0.25초마다 War3.exe 프로세스 존재 체크.
        매크로 실행 중 3초 연속 미감지 시 JNLoader부터 재시작 (UI 버튼 유지)."""
        if not (self._worker and self._worker._running):
            self._war3_gone_ticks = 0
            return
        try:
            alive = any(p.info['name'].lower() == 'war3.exe'
                        for p in psutil.process_iter(['name']))
        except Exception:
            alive = True
        if alive:
            self._war3_gone_ticks = 0
        else:
            self._war3_gone_ticks += 1
            elapsed = self._war3_gone_ticks * 0.25
            self._append_log(
                f"[{now()}] War3 미감지 ({elapsed:.2f}초)...", "warn")
            if self._war3_gone_ticks >= 12:  # 12 × 0.25s = 3초
                self._war3_gone_ticks = 0
                self._append_log(
                    f"[{now()}] War3 프로세스 소멸 → JNLoader 재실행", "error")
                # _pending_recovery 플래그 → _on_worker_finished 에서 재시작 처리
                self._pending_recovery = True
                if self._worker:
                    self._worker.stop()
                if self._thread:
                    self._thread.quit()

    def _start(self):
        # 이미 실행 중이면 무시
        if self._thread and self._thread.isRunning():
            return

        # ── 필수 설정 체크 ────────────────────────────
        cfg = load_config()
        missing = []
        jn_path = cfg.get("jnloader_path", "").strip()
        if not jn_path or not os.path.isfile(os.path.join(jn_path, "JNLoader.exe")):
            missing.append("• JN로더 경로 설정  (JNLoader.exe 를 찾을 수 없음)")
        if cfg.get("role", "freematch") != "freematch" and not cfg.get("room_name", "").strip():
            missing.append("• 방 제목")
        if not decrypt_password(cfg.get("bnet_password", "")).strip():
            missing.append("• 비밀번호")
        if missing:
            QMessageBox.warning(
                self, "설정 확인 필요",
                "다음 항목이 설정되지 않았습니다:\n\n" + "\n".join(missing)
            )
            return

        self._save_password()
        self._save_room_name()
        self._save_path()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._update_status("실행 중...", YELLOW)
        self._append_log(f"[{now()}] 매크로 시작", "info")

        # ── War3 프로세스 상태 체크 ──────────────────
        try:
            war3_alive = any(p.info['name'].lower() == 'war3.exe'
                             for p in psutil.process_iter(['name']))
        except Exception:
            war3_alive = False

        if not war3_alive:
            # War3 없음 → JNLoader 실행 후 워커 시작
            self._append_log(f"[{now()}] War3 프로세스 없음 → JNLoader 실행", "info")
            if not self._launch_jnloader():
                self._on_worker_finished()
                return
            self._start_worker()
        else:
            # War3 있음 → 인게임 여부 확인
            if image_exists("14.인게임체크.png", background=True):
                self._append_log(f"[{now()}] 현재 인게임 접속중...", "info")
                self._append_log(f"[{now()}] 조건에 따른 매크로를 실행하겠습니다", "info")
                self._start_worker(ingame=True)
            else:
                # 인게임 아님 → War3 완전 종료 후 JNLoader 재실행
                self._append_log(f"[{now()}] War3 프로세스 종료 후 재시작합니다.", "warn")
                for p in psutil.process_iter(['name']):
                    if p.info['name'].lower() == 'war3.exe':
                        try:
                            p.kill()
                        except Exception:
                            pass
                QTimer.singleShot(1500, self._relaunch_and_start)

    def _relaunch_and_start(self):
        """War3 종료 후 딜레이를 두고 JNLoader 재실행 + 워커 시작."""
        if not self._launch_jnloader():
            self._on_worker_finished()
            return
        self._start_worker()

    def _start_worker(self, ingame: bool = False):
        """QThread + WatchWorker 생성 및 시작."""
        self._thread = QThread()
        self._worker = WatchWorker(ingame=ingame)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._worker.log_signal.connect(self._append_log)
        self._worker.update_signal.connect(self._update_last_log)
        self._worker.status_signal.connect(self._update_status)
        self._worker.overlay_signal.connect(self._on_overlay_match)
        self._worker.finished.connect(self._on_worker_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_overlay_match(self, cx: int, cy: int, tw: int, th: int):
        if self.btn_overlay_toggle.isChecked():
            self._overlay.show_match(cx, cy, tw, th)

    def _on_unclip_toggled(self, checked: bool):
        update_config("mouse_unclip", checked)
        if checked:
            self._unclip_timer.start()
            self.btn_unclip_toggle.setText("마우스 감금 해제: ON")
            self.btn_unclip_toggle.setStyleSheet(
                f"background-color:{RED}; color:#ffffff; font-weight:bold;"
                f"border:none; border-radius:6px; padding:4px 12px;"
            )
        else:
            self._unclip_timer.stop()
            self.btn_unclip_toggle.setText("마우스 감금 해제: OFF")
            self.btn_unclip_toggle.setStyleSheet("")

    def _on_topmost_toggled(self, checked: bool):
        update_config("topmost", checked)
        self.btn_topmost_toggle.setText("항상 위: ON" if checked else "항상 위: OFF")
        self.btn_topmost_toggle.setStyleSheet(
            f"background-color:{RED}; color:#ffffff; font-weight:bold;"
            f"border:none; border-radius:6px; padding:4px 12px;"
            if checked else ""
        )
        self._set_topmost(checked)

    def _on_overlay_toggled(self, checked: bool):
        update_config("overlay_enabled", checked)
        self.btn_overlay_toggle.setText(
            "이미지 서치 오버레이: ON" if checked else "이미지 서치 오버레이: OFF"
        )
        self.btn_overlay_toggle.setStyleSheet(
            f"background-color:{RED}; color:#ffffff; font-weight:bold;"
            f"border:none; border-radius:6px; padding:4px 12px;"
            if checked else ""
        )
        if not checked:
            self._overlay.clear()

    def _on_worker_finished(self):
        thread = self._thread
        self._thread = None
        self._worker = None
        if thread:
            thread.quit()
            thread.wait(500)   # 스레드가 완전히 종료될 때까지 대기 (최대 0.5초)
                               # wait() 없이 _thread = None → CPython GC → ~QThread() 호출
                               # 스레드 이벤트 루프가 아직 실행 중이면 undefined behavior → 크래시
        self._overlay.clear()

        if self._pending_recovery:
            self._pending_recovery = False
            self._append_log(f"[{now()}] JNLoader 재실행 중...", "warn")
            if self._launch_jnloader():
                self._start_worker()
            else:
                self._append_log(f"[{now()}] JNLoader 실행 실패 → 매크로 중지", "error")
                self.btn_start.setEnabled(True)
                self.btn_stop.setEnabled(False)
                self._update_status("중지됨", TEXT_DIM)
        else:
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self._update_status("중지됨", TEXT_DIM)

    def _on_tab_changed(self, index: int):
        pass

    def _start_admin_toggle_listener(self):
        if not _PYNPUT_OK:
            return
        from pynput import keyboard as _kb
        def _on_press(key):
            if getattr(key, 'vk', None) == 0xC0:  # ` ~ 키
                self._admin_toggle_signal.emit()
        self._admin_toggle_listener = _kb.Listener(on_press=_on_press)
        self._admin_toggle_listener.daemon = True
        self._admin_toggle_listener.start()

    def _on_admin_hotkey(self):
        self.chk_admin.setChecked(not self.chk_admin.isChecked())

    def _start_admin_capture_listener(self):
        if not _PYNPUT_OK:
            return
        self._stop_admin_capture_listener()
        key_name = self.dd_capture_key._current
        if not _PYNPUT_KEY_MAP.get(key_name):
            return

        def _on_press(key):
            if _key_matches(key, key_name):
                coord = _get_cursor_client()
                rgb   = _get_pixel_at_cursor()
                if coord and rgb:
                    r, g, b = rgb
                    text = (f"X: {coord[0]}  Y: {coord[1]}  "
                            f"R: {r}  G: {g}  B: {b}")
                    self._admin_capture_signal.emit(text)

        from pynput import keyboard as _kb
        self._admin_capture_listener = _kb.Listener(on_press=_on_press)
        self._admin_capture_listener.start()

    def _stop_admin_capture_listener(self):
        if self._admin_capture_listener:
            try:
                self._admin_capture_listener.stop()
            except Exception:
                pass
            self._admin_capture_listener = None

    def _on_capture_hotkey_toggled(self, checked: bool):
        if checked and hasattr(self, "chk_admin") and self.chk_admin.isChecked():
            self._start_admin_capture_listener()
        else:
            self._stop_admin_capture_listener()

    def _on_capture_key_changed(self, _key: str):
        if (hasattr(self, "chk_capture") and self.chk_capture.isChecked()
                and hasattr(self, "chk_admin") and self.chk_admin.isChecked()):
            self._start_admin_capture_listener()

    def _on_admin_toggled(self, checked: bool):
        if checked:
            self.lbl_admin_status.setText("ON")
            self.lbl_admin_status.setStyleSheet(f"color:{GREEN};")
            self.chk_capture.setEnabled(True)
            self.dd_capture_key.setEnabled(True)
            self.chk_save.setEnabled(True)
            self.dd_save_key.setEnabled(True)
            self._admin_timer.start()
            if self.chk_capture.isChecked():
                self._start_admin_capture_listener()
            if self.chk_save.isChecked():
                self._start_admin_save_listener()
            self._admin_overlay.show()
        else:
            self.lbl_admin_status.setText("OFF")
            self.lbl_admin_status.setStyleSheet(f"color:{RED};")
            self.chk_capture.setEnabled(False)
            self.dd_capture_key.setEnabled(False)
            self.chk_save.setEnabled(False)
            self.dd_save_key.setEnabled(False)
            self._admin_timer.stop()
            self._stop_admin_capture_listener()
            self._stop_admin_save_listener()
            self._admin_overlay.hide()
            self._unfreeze_admin()
            self._ocr_timer.stop()
            self.btn_ocr_toggle.setChecked(False)
            self.btn_ocr_toggle.setText("▶ 실시간")
            self.lbl_admin_coord.setText("—")
            self.lbl_admin_rgb.setText("—")
            self.lbl_admin_swatch.setStyleSheet(f"background:{DARK_BORDER}; border:1px solid {TEXT_DIM}; border-radius:4px;")

    def _update_admin_display(self):
        cap_key = self.dd_capture_key._current if hasattr(self, "dd_capture_key") else "—"
        if self._admin_frozen:
            # 좌표/RGB 업데이트는 생략하되 오버레이는 계속 따라다님
            self._admin_overlay.refresh(None, None, cap_key, frozen=True)
            self._admin_overlay.follow_cursor()
            return
        coord = _get_cursor_client()
        if coord:
            self.lbl_admin_coord.setText(f"X: {coord[0]:>5d}   Y: {coord[1]:>5d}  [클라이언트]")
        else:
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            coord = (pt.x, pt.y)
            self.lbl_admin_coord.setText(f"X: {coord[0]:>5d}   Y: {coord[1]:>5d}  [윈도우]")

        rgb = _get_pixel_at_cursor()
        if rgb:
            r, g, b = rgb
            self.lbl_admin_rgb.setText(f"R: {r:3d}   G: {g:3d}   B: {b:3d}")
            self.lbl_admin_swatch.setStyleSheet(
                f"background:#{r:02x}{g:02x}{b:02x}; border:1px solid {TEXT_DIM}; border-radius:4px;"
            )
        else:
            self.lbl_admin_rgb.setText("—")
            self.lbl_admin_swatch.setStyleSheet(f"background:{DARK_BORDER}; border:1px solid {TEXT_DIM}; border-radius:4px;")

        # 커서 오버레이 갱신
        self._admin_overlay.refresh(coord, rgb, cap_key, frozen=False)
        self._admin_overlay.follow_cursor()

    def _on_admin_captured(self, text: str):
        QApplication.clipboard().setText(text)
        self.lbl_last_capture.setText(f"[{now()}]  {text}")
        self.lbl_last_capture.setStyleSheet(
            f"color:{GREEN}; background:{DARK_PANEL};"
            f" border:1px solid {DARK_BORDER}; border-radius:4px; padding:4px 8px;"
        )

    def _start_admin_save_listener(self):
        if not _PYNPUT_OK:
            return
        self._stop_admin_save_listener()
        key_name = self.dd_save_key._current
        if not _PYNPUT_KEY_MAP.get(key_name):
            return

        def _on_press(key):
            if _key_matches(key, key_name):
                self._admin_save_signal.emit()

        from pynput import keyboard as _kb
        self._admin_save_listener = _kb.Listener(on_press=_on_press)
        self._admin_save_listener.start()

    def _stop_admin_save_listener(self):
        if self._admin_save_listener:
            try:
                self._admin_save_listener.stop()
            except Exception:
                pass
            self._admin_save_listener = None

    def _on_save_hotkey_toggled(self, checked: bool):
        if checked and hasattr(self, "chk_admin") and self.chk_admin.isChecked():
            self._start_admin_save_listener()
        else:
            self._stop_admin_save_listener()

    def _on_save_key_changed(self, _key: str):
        if (hasattr(self, "chk_save") and self.chk_save.isChecked()
                and hasattr(self, "chk_admin") and self.chk_admin.isChecked()):
            self._start_admin_save_listener()

    def _on_save_hotkey_triggered(self):
        """WC3 화면 캡처 → 화면 정지 + 드래그 영역 선택 오버레이 표시."""
        from PySide6.QtCore import QPoint as _QP
        # 이미 선택 중이면 무시
        if getattr(self, '_snapshot_selector', None) and self._snapshot_selector.isVisible():
            return
        # WC3 창이 있는 모니터의 화면 캡처
        hwnd = find_war3_hwnd()
        if hwnd:
            pt = ctypes.wintypes.POINT(0, 0)
            ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
            screen = QApplication.screenAt(_QP(pt.x, pt.y))
        else:
            screen = None
        if screen is None:
            screen = QApplication.primaryScreen()
        # 화면 전체 스크린샷 (정지 화면용)
        pixmap     = screen.grabWindow(0)
        screen_geo = screen.geometry()
        # 어드민 프리즈
        self._admin_frozen = True
        self.lbl_save_status.setText("⏸ 드래그로 영역을 선택하세요")
        self.lbl_save_status.setStyleSheet(f"color:{YELLOW};")
        # 영역 선택 오버레이 시작
        self._snapshot_selector = SnapshotRegionSelector(pixmap, screen_geo)
        self._snapshot_selector.region_selected.connect(self._on_region_captured)
        self._snapshot_selector.cancelled.connect(self._on_snapshot_cancelled)
        self._snapshot_selector.start()

    def _on_region_captured(self, cropped: "QPixmap"):
        """영역 선택 완료 → 프리뷰 표시 + 저장 UI 활성화."""
        self._snapshot_pixmap = cropped
        preview = cropped.scaled(300, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl_snapshot.setPixmap(preview)
        self.lbl_snapshot.setMinimumHeight(preview.height())
        self.edit_save_name.setEnabled(True)
        self.btn_save_img.setEnabled(True)
        self.btn_cancel_snap.setEnabled(True)
        self.lbl_save_status.setText("⏸ 화면 정지됨 — 파일명 입력 후 저장")
        self.lbl_save_status.setStyleSheet(f"color:{YELLOW};")

    def _on_snapshot_cancelled(self):
        """영역 선택 취소 → 언프리즈."""
        self._unfreeze_admin()

    def _save_snapshot_to_file(self):
        if not self._snapshot_pixmap:
            return
        name = self.edit_save_name.text().strip()
        if not name:
            self.lbl_save_status.setText("파일명을 입력하세요.")
            self.lbl_save_status.setStyleSheet(f"color:{RED};")
            return
        if not name.lower().endswith(".png"):
            name += ".png"
        img_dir  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image_search")
        os.makedirs(img_dir, exist_ok=True)
        out_path = os.path.join(img_dir, name)
        ok = self._snapshot_pixmap.save(out_path, "PNG")
        if ok:
            self.lbl_save_status.setText(f"✅ 저장 완료: {name}")
            self.lbl_save_status.setStyleSheet(f"color:{GREEN};")
            self._unfreeze_admin()
        else:
            self.lbl_save_status.setText(f"❌ 저장 실패")
            self.lbl_save_status.setStyleSheet(f"color:{RED};")

    # ── OCR 모니터 ───────────────────────────────────
    def _start_ocr_select(self):
        self.hide()
        QTimer.singleShot(150, self._do_ocr_freeze)

    def _do_ocr_freeze(self):
        """프라이머리 모니터 캡처 → OcrFrozenSelector 표시."""
        screen = QApplication.primaryScreen()
        screen_geo = screen.geometry()
        pixmap = screen.grabWindow(0)
        sel = OcrFrozenSelector(pixmap, screen_geo)
        sel.region_selected.connect(self._on_ocr_region_selected)
        sel.cancelled.connect(lambda: self.show())
        self._ocr_frozen_selector = sel   # GC 방지
        sel.start()

    def _on_ocr_region_selected(self, rect: "QRect"):
        self._ocr_region = rect
        screen = QApplication.screenAt(rect.topLeft())
        screens = QApplication.screens()
        mon_idx = screens.index(screen) + 1 if screen and screen in screens else "?"
        self.lbl_ocr_region.setText(
            f"모니터 {mon_idx}  ({rect.x()}, {rect.y()})  {rect.width()}×{rect.height()} px"
        )
        self.show()
        self._run_ocr_monitor()

    def _toggle_ocr_realtime(self, checked: bool):
        if checked:
            if not self._ocr_region:
                self.btn_ocr_toggle.setChecked(False)
                return
            self.btn_ocr_toggle.setText("⏹ 중지")
            self._ocr_timer.start(self.spn_ocr_interval.value())
        else:
            self.btn_ocr_toggle.setText("▶ 실시간")
            self._ocr_timer.stop()

    def _run_ocr_monitor(self):
        if not self._ocr_region:
            return
        r = self._ocr_region
        mode = self.cmb_ocr_mode.currentIndex()  # 0=한글, 1=한글+숫자
        try:
            with mss.mss() as sct:
                img = np.array(sct.grab({
                    "top": r.y(), "left": r.x(),
                    "width": r.width(), "height": r.height(),
                }))
            lang = "kor" if mode == 0 else "kor+eng"
            text, _ = _ocr_text(img, lang=lang, psm=7)
            self.lbl_ocr_result.setText(text if text else "?")
            color = ACCENT if text else TEXT_DIM
            self.lbl_ocr_result.setStyleSheet(
                f"background:{DARK_PANEL}; color:{color};"
                f" border:1px solid {DARK_BORDER}; border-radius:6px; padding:6px;"
            )
        except Exception as e:
            self.lbl_ocr_result.setText(f"오류: {e}")
            self.lbl_ocr_result.setStyleSheet(
                f"background:{DARK_PANEL}; color:{RED};"
                f" border:1px solid {DARK_BORDER}; border-radius:6px; padding:6px;"
            )

    def _unfreeze_admin(self):
        self._admin_frozen     = False
        self._snapshot_pixmap  = None
        self.lbl_snapshot.clear()
        self.lbl_snapshot.setText("스냅샷 없음")
        self.lbl_snapshot.setMinimumHeight(120)
        self.edit_save_name.clear()
        self.edit_save_name.setEnabled(False)
        self.btn_save_img.setEnabled(False)
        self.btn_cancel_snap.setEnabled(False)
        self.lbl_save_status.setText("")

    def _stop(self):
        self._war3_gone_ticks = 0
        self._pending_recovery = False
        if self._worker:
            self._worker.stop()
        if self._thread:
            self._thread.quit()
            # wait() 호출 제거 → UI 블로킹 없음
            # 정리는 _on_worker_finished 에서 처리
        self.btn_stop.setEnabled(False)
        self._append_log(f"[{now()}] 매크로 중지", "warn")

    # ── 로그 패널 토글 ────────────────────────────────
    def _update_tab_nav_buttons(self, index: int = -1):
        if index < 0:
            index = self.tabs.currentIndex()
        self._btn_tab_prev.setEnabled(index > 0)
        self._btn_tab_next.setEnabled(index < self.tabs.count() - 1)

    _BASE_MIN_W  = 670   # 메인 패널 최소 폭
    _LOG_MIN_W   = 540   # 로그 패널 최소 폭
    _MIN_H       = 692   # 최소 높이

    def _refresh_logic_panel(self):
        if hasattr(self, "_logic_desc_label") and hasattr(self, "_build_logic_desc"):
            self._logic_desc_label.setText(self._build_logic_desc())

    def _set_logic_btn_checked(self, state: bool):
        for b in getattr(self, "_logic_btns", []):
            b.setChecked(state)

    def _show_side_panel(self, panel: "QWidget", is_logic: bool = False):
        """사이드 패널 하나를 열고, 다른 사이드 패널은 닫는 공통 헬퍼."""
        other_panels = [self.log_panel, self.logic_panel]

        def _set_checked(p, state):
            if p is self.logic_panel:
                self._set_logic_btn_checked(state)
            else:
                self.btn_log_toggle.setChecked(state)

        self.setUpdatesEnabled(False)
        try:
            if panel.isVisible():
                # ── 열린 패널 닫기 ──────────────────────────────
                panel.hide()
                _set_checked(panel, False)
                self._main_panel.setMinimumWidth(0)
                self._main_panel.setMaximumWidth(16777215)
                self.setMinimumSize(self._BASE_MIN_W, self._MIN_H)
                self.resize(getattr(self, "_base_w", self._BASE_MIN_W), self.height())
            else:
                _switching = any(
                    other.isVisible() for other in other_panels if other is not panel
                )
                if _switching:
                    # ── 패널 전환: 창 크기 유지, _base_w 재사용 ──
                    for other in other_panels:
                        if other is not panel and other.isVisible():
                            other.hide()
                            _set_checked(other, False)
                else:
                    # ── 처음 열기: 현재 폭 저장 후 확장 ──────────
                    self._base_w = self.width()
                    self._main_panel.setFixedWidth(self._main_panel.width())
                    self.setMinimumSize(self._BASE_MIN_W + self._LOG_MIN_W, self._MIN_H)
                    self.resize(self._base_w + self._LOG_MIN_W, self.height())
                panel.show()
                _set_checked(panel, True)
        finally:
            self.setUpdatesEnabled(True)

    def _toggle_log_panel(self):
        self._show_side_panel(self.log_panel)

    def _toggle_logic_panel(self):
        self._refresh_logic_panel()
        self._show_side_panel(self.logic_panel, is_logic=True)

    # ── 핫키 다이얼로그 ───────────────────────────────
    def _open_hotkey_dialog(self):
        self._hotkey_dialog_open = True
        dlg = HotkeyDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self._start_hotkey_listener()   # 설정 저장 후 리스너 재시작
            self._append_log(f"[{now()}] 핫키 설정 저장됨", "info")
        self._hotkey_dialog_open = False

    # ── 핫키 리스너 ──────────────────────────────────
    def _start_hotkey_listener(self):
        self._stop_hotkey_listener()
        if not _PYNPUT_OK:
            return
        cfg          = load_config()
        start_name   = cfg.get("hotkey_start_key",   "F2")
        stop_name    = cfg.get("hotkey_stop_key",    "F4")
        start_ctrl   = cfg.get("hotkey_start_ctrl",  False)
        start_alt    = cfg.get("hotkey_start_alt",   False)
        start_shift  = cfg.get("hotkey_start_shift", False)
        stop_ctrl    = cfg.get("hotkey_stop_ctrl",   False)
        stop_alt     = cfg.get("hotkey_stop_alt",    False)
        stop_shift   = cfg.get("hotkey_stop_shift",  False)
        start_pynput = _PYNPUT_KEY_MAP.get(start_name)
        stop_pynput  = _PYNPUT_KEY_MAP.get(stop_name)
        emitter      = self._hotkey_emitter

        _CTRL_KEYS  = {_kb.Key.ctrl,  _kb.Key.ctrl_l,  _kb.Key.ctrl_r}
        _ALT_KEYS   = {_kb.Key.alt,   _kb.Key.alt_l,   _kb.Key.alt_r}
        _SHIFT_KEYS = {_kb.Key.shift, _kb.Key.shift_l, _kb.Key.shift_r}
        _ALL_MODS   = _CTRL_KEYS | _ALT_KEYS | _SHIFT_KEYS
        _pressed: set = set()

        def _mods_ok(need_ctrl, need_alt, need_shift):
            if need_ctrl  and not (_pressed & _CTRL_KEYS):  return False
            if need_alt   and not (_pressed & _ALT_KEYS):   return False
            if need_shift and not (_pressed & _SHIFT_KEYS): return False
            return True

        def on_press(key):
            try:
                if getattr(self, '_hotkey_dialog_open', False):
                    return
                if key in _ALL_MODS:
                    _pressed.add(key); return
                if _key_matches(key, start_name) and _mods_ok(start_ctrl, start_alt, start_shift):
                    emitter.start_pressed.emit(); return
                if _key_matches(key, stop_name)  and _mods_ok(stop_ctrl,  stop_alt,  stop_shift):
                    emitter.stop_pressed.emit()
            except Exception:
                pass

        def on_release(key):
            _pressed.discard(key)

        self._hotkey_listener = _kb.Listener(on_press=on_press, on_release=on_release)
        self._hotkey_listener.start()

    def _stop_hotkey_listener(self):
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, '_topmost_initialized', False):
            self._topmost_initialized = True
            self._set_topmost(load_config().get("topmost", True))

    def _set_topmost(self, on: bool):
        import win32gui
        import win32con
        win32gui.SetWindowPos(
            int(self.winId()),
            win32con.HWND_TOPMOST if on else win32con.HWND_NOTOPMOST,
            0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
        )

    def closeEvent(self, event):
        self._war3_monitor.stop()
        self._stop_hotkey_listener()
        self._stop_admin_save_listener()
        if self._worker:
            self._worker.stop()
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)  # 종료 시에만 대기 (UI 닫히는 중)
        event.accept()


# ══════════════════════════════════════════════════
#  진입점
# ══════════════════════════════════════════════════
def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


if __name__ == "__main__":
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable,
            " ".join(f'"{a}"' for a in sys.argv),
            None, 1
        )
        sys.exit()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()

    # 스마트키 저장 상태 복원
    _cfg = load_config()
    if _cfg.get("smart_key_enabled", False):
        hero_vk = ord(str(_cfg.get("hero_group", 1)))
        _smart_hook.start(hero_vk)
    win._on_chat_cmd_changed()

    sys.exit(app.exec())
