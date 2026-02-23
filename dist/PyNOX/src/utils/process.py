"""
utils/process.py — War3 프로세스/HWND 유틸
"""
import ctypes
import ctypes.wintypes
import time
import win32gui


def find_war3_hwnd() -> "int | None":
    """Warcraft III 창 핸들 반환. 없으면 None."""
    found = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if any(k in title for k in ("Warcraft", "warcraft", "War3", "워크")):
            found.append(hwnd)

    win32gui.EnumWindows(_cb, None)
    return found[0] if found else None


def kill_war3() -> bool:
    """Warcraft III 프로세스 강제 종료. 성공 시 True."""
    hwnd = find_war3_hwnd()
    if not hwnd:
        return False
    pid = ctypes.c_ulong(0)
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return False
    handle = ctypes.windll.kernel32.OpenProcess(0x0001, False, pid.value)  # PROCESS_TERMINATE
    if not handle:
        return False
    ctypes.windll.kernel32.TerminateProcess(handle, 0)
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def wait_for_hwnd(timeout: float = 60.0, interval: float = 1.0) -> "int | None":
    """War3 창 핸들이 나타날 때까지 최대 timeout초 대기. 없으면 None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = find_war3_hwnd()
        if hwnd:
            return hwnd
        time.sleep(interval)
    return None
