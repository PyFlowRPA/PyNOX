"""
utils/chat.py — 인게임 채팅 전송 유틸 (standalone)
"""
import ctypes
import ctypes.wintypes
import time
from typing import Callable, Optional

from src.core.input import (
    _user32, _KBD_INPUT,
    _KEYEVENTF_KEYUP,
    _VK_RETURN, _VK_CONTROL, _VK_V,
    _press_vk, type_string, press_enter,
)
from src.utils.process import find_war3_hwnd


def send_ingame_chat(text: str, log: "Optional[Callable]" = None):
    """Enter → 텍스트 입력 → Enter 로 인게임 채팅 전송."""
    hwnd = find_war3_hwnd()
    if hwnd:
        _user32.SetForegroundWindow(hwnd)
        time.sleep(0.1)
    if log:
        log(f"채팅 입력: {text}", "info")
    _press_vk(_VK_RETURN); time.sleep(0.1)
    _press_vk(_VK_RETURN, keyup=True); time.sleep(0.2)
    type_string(text)
    time.sleep(0.1)
    _press_vk(_VK_RETURN); time.sleep(0.02)
    _press_vk(_VK_RETURN, keyup=True)
    if log:
        log(f"채팅 전송 완료: {text}", "success")


def send_chat_fast(text: str, log: "Optional[Callable]" = None):
    """클립보드 붙여넣기 방식으로 빠르게 채팅 커맨드 전송."""
    import win32clipboard
    hwnd = find_war3_hwnd()
    if not hwnd:
        if log:
            log("[채팅] WC3 창 없음", "warn")
        return
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()
    _user32.SetForegroundWindow(hwnd)
    time.sleep(0.05)
    _press_vk(_VK_RETURN);              time.sleep(0.02)
    _press_vk(_VK_RETURN, keyup=True);  time.sleep(0.05)
    _press_vk(_VK_CONTROL)
    _press_vk(_VK_V);                   time.sleep(0.02)
    _press_vk(_VK_V, keyup=True)
    _press_vk(_VK_CONTROL, keyup=True); time.sleep(0.05)
    _press_vk(_VK_RETURN);              time.sleep(0.02)
    _press_vk(_VK_RETURN, keyup=True)
    if log:
        log(f"[채팅] 전송: {text}", "success")


def send_chat_instant(text: str, log: "Optional[Callable]" = None):
    """배치 SendInput으로 딜레이 없이 채팅 커맨드 전송."""
    import win32clipboard
    hwnd = find_war3_hwnd()
    if not hwnd:
        if log:
            log("[채팅] WC3 창 없음", "warn")
        return
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()
    _user32.SetForegroundWindow(hwnd)
    events = [
        (_VK_RETURN,  0),
        (_VK_RETURN,  _KEYEVENTF_KEYUP),
        (_VK_CONTROL, 0),
        (_VK_V,       0),
        (_VK_V,       _KEYEVENTF_KEYUP),
        (_VK_CONTROL, _KEYEVENTF_KEYUP),
        (_VK_RETURN,  0),
        (_VK_RETURN,  _KEYEVENTF_KEYUP),
    ]
    arr = (_KBD_INPUT * len(events))()
    for i, (vk, flags) in enumerate(events):
        ctypes.memset(ctypes.byref(arr[i]), 0, ctypes.sizeof(_KBD_INPUT))
        arr[i].type       = 1
        arr[i].ki.wVk     = vk
        arr[i].ki.wScan   = _user32.MapVirtualKeyW(vk, 0)
        arr[i].ki.dwFlags = flags
    _user32.SendInput(len(events), arr, ctypes.sizeof(_KBD_INPUT))
    if log:
        log(f"[채팅] 즉시 전송: {text}", "success")
