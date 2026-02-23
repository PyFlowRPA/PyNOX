"""
utils/smartkey.py — WH_KEYBOARD_LL 저수준 키보드 후킹 (스마트키)
"""
import ctypes
import ctypes.wintypes
import os
import queue
import threading
import time

from src.core.input import (
    _user32, _KBD_INPUT, _MOUSE_INPUT,
    _KEYEVENTF_KEYUP, _MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP,
)
from src.utils.process import find_war3_hwnd


_SMART_VKS = frozenset([
    0x51, 0x57, 0x45, 0x52, 0x54,  # Q W E R T
    0x41, 0x44, 0x46, 0x47,         # A D F G
    0x5A, 0x58, 0x43, 0x56,         # Z X C V
])
_WH_KEYBOARD_LL  = 0xD
_WM_KEYDOWN      = 0x0100
_LLKHF_INJECTED  = 0x10


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('vkCode',      ctypes.c_ulong),
        ('scanCode',    ctypes.c_ulong),
        ('flags',       ctypes.c_ulong),
        ('time',        ctypes.c_ulong),
        ('dwExtraInfo', ctypes.c_size_t),
    ]


_HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p
)


class SmartKeyHookManager:
    """저수준 키보드 후크로 스마트키 구현.
    콜백에서 큐에 적재 → 별도 sender 스레드에서 SendInput 처리.
    """

    def __init__(self):
        self._hook_id      = None
        self._hook_proc    = None
        self._active       = False
        self._smart_active = False
        self._hero_vk      = 0x31
        self._chat_open    = False
        self._in_game      = False
        self._queue: "queue.Queue" = queue.Queue()
        self._chat_cmds: dict = {}
        self._chat_queue: "queue.Queue" = queue.Queue()
        self._exit_vk      = 0
        self._generation   = 0  # 스레드 세대 카운터 — 중복 기동 방지

    # ── 채팅 & 인게임 상태 폴링 ──────────────────────
    def _poll_chat(self, gen: int):
        import pymem
        import pymem.process
        pm = None
        base = 0
        while self._active and self._generation == gen:
            try:
                if pm is None:
                    pm = pymem.Pymem("war3.exe")
                    base = 0
                    for mod in pymem.process.enum_process_module(pm.process_handle):
                        if os.path.basename(mod.name).lower() == "game.dll":
                            base = mod.lpBaseOfDll
                            break
                if base:
                    self._chat_open = bool(pm.read_int(base + 0xD04FEC))
                    a = pm.read_int(base + 0xD32318)
                    b = pm.read_int(base + 0xD3231C)
                    self._in_game = (a == 4 and b == 4) or \
                                    (a == 1 and b == 1)
            except Exception:
                pm = None
                base = 0
                self._chat_open = False
                self._in_game   = False
            time.sleep(0.05)

    # ── 키 전송 스레드 (SendInput은 항상 여기서) ──────
    def _sender(self, gen: int):
        while self._active and self._generation == gen:
            try:
                vk, hero_vk = self._queue.get(timeout=0.1)

                def _kb(k, f):
                    inp = _KBD_INPUT()
                    ctypes.memset(ctypes.byref(inp), 0, ctypes.sizeof(inp))
                    inp.type       = 1
                    inp.ki.wVk     = k
                    inp.ki.wScan   = _user32.MapVirtualKeyW(k, 0)
                    inp.ki.dwFlags = f
                    return inp

                def _ms(flags):
                    inp = _MOUSE_INPUT()
                    ctypes.memset(ctypes.byref(inp), 0, ctypes.sizeof(inp))
                    inp.type       = 0
                    inp.mi.dwFlags = flags
                    return inp

                sz  = ctypes.sizeof(_KBD_INPUT)
                arr = (_KBD_INPUT * 6)()

                def _copy(dst, src):
                    ctypes.memmove(ctypes.byref(dst), ctypes.byref(src), sz)

                _copy(arr[0], _kb(vk,      0))
                _copy(arr[1], _kb(vk,      _KEYEVENTF_KEYUP))
                _copy(arr[2], _ms(_MOUSEEVENTF_LEFTDOWN))
                _copy(arr[3], _ms(_MOUSEEVENTF_LEFTUP))
                _copy(arr[4], _kb(hero_vk, 0))
                _copy(arr[5], _kb(hero_vk, _KEYEVENTF_KEYUP))

                _user32.SendInput(6, arr, sz)

            except queue.Empty:
                pass
            except Exception:
                pass

    # ── 채팅 커맨드 전송 스레드 ────────────────────────
    def _chat_sender(self, gen: int):
        from src.utils.memory import send_chat_memory
        while self._active and self._generation == gen:
            try:
                text = self._chat_queue.get(timeout=0.1)
                hwnd = find_war3_hwnd()
                if hwnd:
                    send_chat_memory(hwnd, text, hide=True)
            except queue.Empty:
                pass
            except Exception:
                pass

    # ── 후킹 스레드 (메시지 루프) ────────────────────
    def _hook_thread_func(self, gen: int):
        def _callback(nCode, wParam, lParam):
            if nCode >= 0 and wParam == _WM_KEYDOWN:
                ks = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                if not (ks.flags & _LLKHF_INJECTED):
                    vk = ks.vkCode
                    if vk in _SMART_VKS:
                        hwnd = find_war3_hwnd()
                        if hwnd and _user32.GetForegroundWindow() == hwnd:
                            if self._in_game and not self._chat_open:
                                self._queue.put((vk, self._hero_vk))
                                return 1
                    if vk in self._chat_cmds:
                        hwnd = find_war3_hwnd()
                        if hwnd and _user32.GetForegroundWindow() == hwnd:
                            if self._in_game and not self._chat_open:
                                self._chat_queue.put(self._chat_cmds[vk])
                                return 1
                    if self._exit_vk and vk == self._exit_vk:
                        hwnd = find_war3_hwnd()
                        if hwnd and _user32.GetForegroundWindow() == hwnd:
                            from src.utils.process import kill_war3
                            kill_war3()
                            return 1
            return _user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

        self._hook_proc = _HOOKPROC(_callback)
        _user32.SetWindowsHookExW.restype  = ctypes.c_void_p
        _user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint
        ]
        _user32.CallNextHookEx.restype  = ctypes.c_long
        _user32.CallNextHookEx.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p
        ]
        _user32.PeekMessageW.restype  = ctypes.c_bool
        _user32.PeekMessageW.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_uint, ctypes.c_uint, ctypes.c_uint
        ]
        self._hook_id = _user32.SetWindowsHookExW(
            _WH_KEYBOARD_LL, self._hook_proc, None, 0
        )
        msg = ctypes.wintypes.MSG()
        hook_id = self._hook_id   # 이 스레드 소유 훅 ID를 로컬에 저장
        while self._active and self._generation == gen:
            if _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.005)
        if hook_id:
            _user32.UnhookWindowsHookEx(hook_id)
            if self._hook_id == hook_id:   # 아직 덮어쓰이지 않은 경우만 초기화
                self._hook_id = None

    def _start_threads(self):
        self._generation += 1
        gen = self._generation
        threading.Thread(target=self._poll_chat,        args=(gen,), daemon=True).start()
        threading.Thread(target=self._sender,           args=(gen,), daemon=True).start()
        threading.Thread(target=self._chat_sender,      args=(gen,), daemon=True).start()
        threading.Thread(target=self._hook_thread_func, args=(gen,), daemon=True).start()

    def start(self, hero_vk: int):
        self._hero_vk      = hero_vk
        self._smart_active = True
        if not self._active:
            self._active = True
            self._start_threads()

    def stop(self):
        self._smart_active = False
        if not self._chat_cmds and not self._exit_vk:
            self._active = False

    def update_chat_cmds(self, cmds: dict):
        self._chat_cmds = cmds
        if cmds and not self._active:
            self._active = True
            self._start_threads()
        elif not cmds and not self._smart_active and not self._exit_vk:
            self._active = False

    def update_exit_cmd(self, vk: int):
        self._exit_vk = vk
        if vk and not self._active:
            self._active = True
            self._start_threads()
        elif not vk and not self._smart_active and not self._chat_cmds:
            self._active = False


# 싱글턴 인스턴스
_smart_hook = SmartKeyHookManager()
