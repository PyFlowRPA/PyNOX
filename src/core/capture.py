"""
core/capture.py — 화면 캡처 (PrintWindow + ImageGrab)
GDI 리소스 누수 수정: 각 리소스를 개별 try 블록으로 해제
"""
import ctypes
import ctypes.wintypes

import cv2
import numpy as np
import win32gui
import win32ui
from PIL import ImageGrab

from src.utils.process import find_war3_hwnd

_user32 = ctypes.windll.user32


# ══════════════════════════════════════════════════
#  PrintWindow 기반 캡처 (백그라운드 동작)
# ══════════════════════════════════════════════════
def _printwindow_capture(hwnd: int, as_bgr: bool = False) -> "np.ndarray | None":
    """GDI 핸들 누수 없이 PrintWindow 캡처.
    as_bgr=True 이면 BGR, False 이면 GRAY 반환.
    PW_CLIENTONLY | PW_RENDERFULLCONTENT = 3"""
    hwnd_dc = None
    mfc_dc  = None
    save_dc = None
    bmp     = None
    try:
        rc = ctypes.wintypes.RECT()
        _user32.GetClientRect(hwnd, ctypes.byref(rc))
        w, h = rc.right, rc.bottom
        if w <= 0 or h <= 0:
            return None

        hwnd_dc = win32gui.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None
        mfc_dc  = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp     = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bmp)

        ok = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)
        if ok:
            bits = bmp.GetBitmapBits(True)
            arr  = np.frombuffer(bits, dtype=np.uint8).reshape(h, w, 4)
            if as_bgr:
                return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            return cv2.cvtColor(arr, cv2.COLOR_BGRA2GRAY)
        return None
    except Exception:
        return None
    finally:
        # 각 리소스를 개별 try 블록으로 해제 (하나 실패해도 나머지 해제 보장)
        if bmp is not None:
            try:
                win32gui.DeleteObject(bmp.GetHandle())
            except Exception:
                pass
        if save_dc is not None:
            try:
                save_dc.DeleteDC()
            except Exception:
                pass
        if mfc_dc is not None:
            try:
                mfc_dc.DeleteDC()
            except Exception:
                pass
        if hwnd_dc is not None:
            try:
                win32gui.ReleaseDC(hwnd, hwnd_dc)
            except Exception:
                pass


# ── 퍼블릭 API (하위 호환) ───────────────────────────────────────────────────
def _capture_war3_gray_background() -> "np.ndarray | None":
    """PrintWindow API로 WC3 창을 백그라운드에서 그레이스케일 캡처."""
    hwnd = find_war3_hwnd()
    return _printwindow_capture(hwnd, as_bgr=False) if hwnd else None


def _capture_war3_bgr_background() -> "np.ndarray | None":
    """PrintWindow API로 WC3 창을 백그라운드에서 컬러(BGR) 캡처."""
    hwnd = find_war3_hwnd()
    return _printwindow_capture(hwnd, as_bgr=True) if hwnd else None


# ══════════════════════════════════════════════════
#  ImageGrab 기반 캡처 (포어그라운드 전용)
# ══════════════════════════════════════════════════
def _imagegrab_capture(as_bgr: bool = False) -> "np.ndarray | None":
    """ImageGrab 기반 캡처 (창모드/포어그라운드 전용)."""
    hwnd = find_war3_hwnd()
    if not hwnd:
        return None
    pt = ctypes.wintypes.POINT(0, 0)
    _user32.ClientToScreen(hwnd, ctypes.byref(pt))
    rc = ctypes.wintypes.RECT()
    _user32.GetClientRect(hwnd, ctypes.byref(rc))
    w, h = rc.right, rc.bottom
    if w <= 0 or h <= 0:
        return None
    bbox = (pt.x, pt.y, pt.x + w, pt.y + h)
    try:
        arr = np.array(ImageGrab.grab(bbox))
        if arr.size == 0 or arr.ndim < 3:
            return None
        if as_bgr:
            if arr.shape[2] == 4:
                return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        else:
            if arr.shape[2] == 4:
                return cv2.cvtColor(arr, cv2.COLOR_RGBA2GRAY)
            return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    except Exception:
        return None


def _capture_war3_gray() -> "np.ndarray | None":
    """WC3 클라이언트 영역을 그레이스케일로 캡처 (ImageGrab)."""
    return _imagegrab_capture(as_bgr=False)


def _capture_war3_bgr() -> "np.ndarray | None":
    """WC3 클라이언트 영역을 컬러(BGR)로 캡처 (ImageGrab)."""
    return _imagegrab_capture(as_bgr=True)


# ══════════════════════════════════════════════════
#  픽셀 유틸
# ══════════════════════════════════════════════════
def _get_pixel_at_client(cx: int, cy: int) -> "tuple[int, int, int] | None":
    """WC3 클라이언트 좌표 (cx, cy) 의 픽셀 RGB 반환 (PrintWindow — 백그라운드 가능)."""
    hwnd = find_war3_hwnd()
    if not hwnd:
        return None
    hwnd_dc = None
    mfc_dc  = None
    save_dc = None
    bmp     = None
    try:
        rc = ctypes.wintypes.RECT()
        _user32.GetClientRect(hwnd, ctypes.byref(rc))
        w, h = rc.right, rc.bottom
        if w <= 0 or h <= 0 or cx < 0 or cx >= w or cy < 0 or cy >= h:
            return None

        hwnd_dc = win32gui.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None
        mfc_dc  = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp     = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bmp)

        ok = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)
        if ok:
            bits = bmp.GetBitmapBits(True)
            arr  = np.frombuffer(bits, dtype=np.uint8).reshape(h, w, 4)
            b, g, r = int(arr[cy, cx, 0]), int(arr[cy, cx, 1]), int(arr[cy, cx, 2])
            return (r, g, b)
        return None
    except Exception:
        return None
    finally:
        if bmp is not None:
            try:
                win32gui.DeleteObject(bmp.GetHandle())
            except Exception:
                pass
        if save_dc is not None:
            try:
                save_dc.DeleteDC()
            except Exception:
                pass
        if mfc_dc is not None:
            try:
                mfc_dc.DeleteDC()
            except Exception:
                pass
        if hwnd_dc is not None:
            try:
                win32gui.ReleaseDC(hwnd, hwnd_dc)
            except Exception:
                pass


def _get_cursor_client() -> "tuple[int, int] | None":
    """WC3 클라이언트 좌표계 기준 커서 위치 반환."""
    hwnd = find_war3_hwnd()
    if not hwnd:
        return None
    pt = ctypes.wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    _user32.ScreenToClient(hwnd, ctypes.byref(pt))
    return (pt.x, pt.y)


def _get_pixel_at_cursor() -> "tuple[int, int, int] | None":
    """현재 커서 스크린 위치의 픽셀 RGB 반환."""
    pt = ctypes.wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    dc = ctypes.windll.user32.GetDC(0)
    color = ctypes.windll.gdi32.GetPixel(dc, pt.x, pt.y)
    ctypes.windll.user32.ReleaseDC(0, dc)
    if color == 0xFFFFFFFF:
        return None
    return (color & 0xFF, (color >> 8) & 0xFF, (color >> 16) & 0xFF)
