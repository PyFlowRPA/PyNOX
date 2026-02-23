"""
core/input.py — 키보드/마우스 SendInput 유틸
"""
import ctypes
import ctypes.wintypes
import time

_user32 = ctypes.windll.user32

# ── 마우스 이벤트 플래그 ─────────────────────────────────────────────────────
_MOUSEEVENTF_LEFTDOWN  = 0x0002
_MOUSEEVENTF_LEFTUP    = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP   = 0x0010

# ── 키보드 이벤트 플래그 ─────────────────────────────────────────────────────
_KEYEVENTF_UNICODE     = 0x0004
_KEYEVENTF_KEYUP       = 0x0002
_KEYEVENTF_EXTENDEDKEY = 0x0001

# ── 가상 키 코드 ─────────────────────────────────────────────────────────────
_VK_RETURN  = 0x0D
_VK_ESCAPE  = 0x1B
_VK_TAB     = 0x09
_VK_SHIFT   = 0x10
_VK_CONTROL = 0x11
_VK_HANGUL  = 0x15
_VK_LEFT    = 0x25
_VK_RIGHT   = 0x27
_VK_MENU    = 0x12   # Alt
_VK_S       = ord('S')
_VK_C       = ord('C')
_VK_G       = ord('G')
_VK_V       = ord('V')

# ── 포탈 키별 클릭 좌표 (Q~C 순) ────────────────────────────────────────────
_PORTAL_COORDS: "dict[str, tuple[int, int]]" = {
    "Q 포탈 | 라하린 숲":       (1535,  870),
    "W 포탈 | 아스탈 요새":     (1635,  870),
    "E 포탈 | 어둠얼음성채":    (1740,  870),
    "R 포탈 | 버려진 고성":     (1850,  875),
    "A 포탈 | 바위협곡":        (1535,  950),
    "S 포탈 | 바람의 협곡":     (1655,  950),
    "D 포탈 | 시계태엽 공장":   (1740,  950),
    "F 포탈 | 속삭임의 숲":     (1855,  950),
    "Z 포탈 | 이그니스영역":    (1535, 1030),
    "X 포탈 | 정령계":          (1640, 1030),
    "C 포탈":                   (1735, 1030),
}

# ── 두벌식 자모 매핑 ─────────────────────────────────────────────────────────
_JAMO_VK = {
    'ㄱ': (ord('R'), False), 'ㄲ': (ord('R'), True),
    'ㄴ': (ord('S'), False), 'ㄷ': (ord('E'), False), 'ㄸ': (ord('E'), True),
    'ㄹ': (ord('F'), False), 'ㅁ': (ord('A'), False), 'ㅂ': (ord('Q'), False),
    'ㅃ': (ord('Q'), True),  'ㅅ': (ord('T'), False), 'ㅆ': (ord('T'), True),
    'ㅇ': (ord('D'), False), 'ㅈ': (ord('W'), False), 'ㅉ': (ord('W'), True),
    'ㅊ': (ord('C'), False), 'ㅋ': (ord('Z'), False), 'ㅌ': (ord('X'), False),
    'ㅍ': (ord('V'), False), 'ㅎ': (ord('G'), False),
    'ㅏ': (ord('K'), False), 'ㅐ': (ord('O'), False),
    'ㅑ': (ord('I'), False), 'ㅒ': (ord('O'), True),
    'ㅓ': (ord('J'), False), 'ㅔ': (ord('P'), False),
    'ㅕ': (ord('U'), False), 'ㅖ': (ord('P'), True),
    'ㅗ': (ord('H'), False), 'ㅛ': (ord('Y'), False),
    'ㅜ': (ord('N'), False), 'ㅠ': (ord('B'), False),
    'ㅡ': (ord('M'), False), 'ㅣ': (ord('L'), False),
}
_CHOSUNG  = ['ㄱ','ㄲ','ㄴ','ㄷ','ㄸ','ㄹ','ㅁ','ㅂ','ㅃ','ㅅ','ㅆ','ㅇ','ㅈ','ㅉ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ']
_JUNGSUNG = ['ㅏ','ㅐ','ㅑ','ㅒ','ㅓ','ㅔ','ㅕ','ㅖ','ㅗ','ㅘ','ㅙ','ㅚ','ㅛ','ㅜ','ㅝ','ㅞ','ㅟ','ㅠ','ㅡ','ㅢ','ㅣ']
_JONGSUNG = ['','ㄱ','ㄲ','ㄳ','ㄴ','ㄵ','ㄶ','ㄷ','ㄹ','ㄺ','ㄻ','ㄼ','ㄽ','ㄾ','ㄿ','ㅀ','ㅁ','ㅂ','ㅄ','ㅅ','ㅆ','ㅇ','ㅈ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ']
_COMPOUND_JUNG = {'ㅘ':'ㅗㅏ','ㅙ':'ㅗㅐ','ㅚ':'ㅗㅣ','ㅝ':'ㅜㅓ','ㅞ':'ㅜㅔ','ㅟ':'ㅜㅣ','ㅢ':'ㅡㅣ'}
_COMPOUND_JONG = {'ㄳ':'ㄱㅅ','ㄵ':'ㄴㅈ','ㄶ':'ㄴㅎ','ㄺ':'ㄹㄱ','ㄻ':'ㄹㅁ','ㄼ':'ㄹㅂ','ㄽ':'ㄹㅅ','ㄾ':'ㄹㅌ','ㄿ':'ㄹㅍ','ㅀ':'ㄹㅎ','ㅄ':'ㅂㅅ'}


def _decompose_jamos(ch: str) -> list:
    code = ord(ch) - 0xAC00
    if not (0 <= code <= 11171):
        return []
    jong_idx = code % 28
    code //= 28
    jung = _JUNGSUNG[code % 21]
    cho  = _CHOSUNG[code // 21]
    jamos = [cho] + list(_COMPOUND_JUNG.get(jung, jung))
    if jong_idx:
        jong = _JONGSUNG[jong_idx]
        jamos += list(_COMPOUND_JONG.get(jong, jong))
    return jamos


# ── ctypes 입력 구조체 ────────────────────────────────────────────────────────
class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.c_long),
        ("dy",          ctypes.c_long),
        ("mouseData",   ctypes.c_ulong),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _MOUSE_INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("_pad", ctypes.c_byte * 32)]
    _anonymous_ = ("_u",)
    _fields_    = [("type", ctypes.c_ulong), ("_u", _U)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         ctypes.c_ushort),
        ("wScan",       ctypes.c_ushort),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KBD_INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("_pad", ctypes.c_byte * 32)]
    _anonymous_ = ("_u",)
    _fields_    = [("type", ctypes.c_ulong), ("_u", _U)]


# ── 전송 헬퍼 ─────────────────────────────────────────────────────────────────
def _send_mouse_click(flags: int):
    """SendInput으로 마우스 클릭 이벤트 전송."""
    inp = _MOUSE_INPUT()
    ctypes.memset(ctypes.byref(inp), 0, ctypes.sizeof(inp))
    inp.type       = 0
    inp.mi.dwFlags = flags
    _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _send_key(vk: int = 0, scan: int = 0, flags: int = 0):
    inp = _KBD_INPUT()
    ctypes.memset(ctypes.byref(inp), 0, ctypes.sizeof(inp))
    inp.type       = 1
    inp.ki.wVk     = vk
    inp.ki.wScan   = scan
    inp.ki.dwFlags = flags
    _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _press_vk(vk: int, keyup: bool = False, extended: bool = False):
    scan  = _user32.MapVirtualKeyW(vk, 0)
    flags = 0
    if keyup:    flags |= _KEYEVENTF_KEYUP
    if extended: flags |= _KEYEVENTF_EXTENDEDKEY
    _send_key(vk, scan, flags)


def type_string(text: str):
    """ASCII + 한글(두벌식) 문자열을 SendInput으로 타이핑."""
    in_korean = False
    for ch in text:
        is_syllable = 0xAC00 <= ord(ch) <= 0xD7A3
        is_jamo     = 0x3131 <= ord(ch) <= 0x3163

        if is_syllable:
            if not in_korean:
                _press_vk(_VK_HANGUL); time.sleep(0.02)
                _press_vk(_VK_HANGUL, keyup=True); time.sleep(0.2)
                in_korean = True
            for jamo in _decompose_jamos(ch):
                vk, need_shift = _JAMO_VK.get(jamo, (None, False))
                if vk is None: continue
                if need_shift:
                    _press_vk(_VK_SHIFT); time.sleep(0.02)
                _press_vk(vk); time.sleep(0.02)
                _press_vk(vk, keyup=True)
                if need_shift:
                    time.sleep(0.02); _press_vk(_VK_SHIFT, keyup=True)
                time.sleep(0.08)

        elif is_jamo:
            if not in_korean:
                _press_vk(_VK_HANGUL); time.sleep(0.02)
                _press_vk(_VK_HANGUL, keyup=True); time.sleep(0.2)
                in_korean = True
            comps = list(_COMPOUND_JONG.get(ch, _COMPOUND_JUNG.get(ch, ch)))
            for comp in comps:
                vk, need_shift = _JAMO_VK.get(comp, (None, False))
                if vk is None: continue
                if need_shift:
                    _press_vk(_VK_SHIFT); time.sleep(0.02)
                _press_vk(vk); time.sleep(0.02)
                _press_vk(vk, keyup=True)
                if need_shift:
                    time.sleep(0.02); _press_vk(_VK_SHIFT, keyup=True)
                time.sleep(0.05)
            _press_vk(_VK_RIGHT, extended=True); time.sleep(0.02)
            _press_vk(_VK_RIGHT, keyup=True, extended=True); time.sleep(0.08)

        else:
            if in_korean:
                _press_vk(_VK_HANGUL); time.sleep(0.02)
                _press_vk(_VK_HANGUL, keyup=True); time.sleep(0.2)
                in_korean = False
            code = ord(ch)
            _send_key(0, code, _KEYEVENTF_UNICODE); time.sleep(0.02)
            _send_key(0, code, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP); time.sleep(0.05)

    time.sleep(0.2)


def press_enter():
    """엔터키 SendInput."""
    _press_vk(_VK_RETURN)
    time.sleep(0.05)
    _press_vk(_VK_RETURN, keyup=True)


def click_image_center(client_x: int, client_y: int) -> bool:
    """WC3 클라이언트 좌표 → 스크린 좌표 변환 후 좌클릭."""
    from src.utils.process import find_war3_hwnd
    hwnd = find_war3_hwnd()
    if not hwnd:
        return False
    pt = ctypes.wintypes.POINT(client_x, client_y)
    _user32.ClientToScreen(hwnd, ctypes.byref(pt))
    _user32.SetCursorPos(pt.x, pt.y)
    time.sleep(0.05)
    _send_mouse_click(_MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.05)
    _send_mouse_click(_MOUSEEVENTF_LEFTUP)
    return True


def right_click_image_center(client_x: int, client_y: int) -> bool:
    """WC3 클라이언트 좌표 → 스크린 좌표 변환 후 우클릭."""
    from src.utils.process import find_war3_hwnd
    hwnd = find_war3_hwnd()
    if not hwnd:
        return False
    pt = ctypes.wintypes.POINT(client_x, client_y)
    _user32.ClientToScreen(hwnd, ctypes.byref(pt))
    _user32.SetCursorPos(pt.x, pt.y)
    time.sleep(0.05)
    _send_mouse_click(_MOUSEEVENTF_RIGHTDOWN)
    time.sleep(0.05)
    _send_mouse_click(_MOUSEEVENTF_RIGHTUP)
    return True


def move_cursor_to(client_x: int, client_y: int) -> bool:
    """WC3 클라이언트 좌표 → 스크린 좌표 변환 후 커서만 이동."""
    from src.utils.process import find_war3_hwnd
    hwnd = find_war3_hwnd()
    if not hwnd:
        return False
    pt = ctypes.wintypes.POINT(client_x, client_y)
    _user32.ClientToScreen(hwnd, ctypes.byref(pt))
    _user32.SetCursorPos(pt.x, pt.y)
    return True


def _scale_coords(ref_x: int, ref_y: int) -> "tuple[int, int]":
    """1920×1080 기준 좌표를 현재 WC3 클라이언트 해상도 비율로 보정."""
    from src.utils.process import find_war3_hwnd
    hwnd = find_war3_hwnd()
    if not hwnd:
        return ref_x, ref_y
    rc = ctypes.wintypes.RECT()
    _user32.GetClientRect(hwnd, ctypes.byref(rc))
    sw, sh = rc.right, rc.bottom
    if sw <= 0 or sh <= 0:
        return ref_x, ref_y
    _REF_W, _REF_H = 1920, 1080
    return int(ref_x * sw / _REF_W), int(ref_y * sh / _REF_H)
