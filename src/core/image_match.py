"""
core/image_match.py — 템플릿 매칭 + LRU 캐시
"""
import os
import sys
from functools import lru_cache

import cv2
import numpy as np

from src.core.capture import (
    _capture_war3_gray, _capture_war3_gray_background,
    _capture_war3_bgr,  _capture_war3_bgr_background,
)


def _resource_path(rel: str) -> str:
    if getattr(sys, "frozen", False):
        # exe 옆 src/ 폴더에 assets, image_search 등이 있음
        base = os.path.join(os.path.dirname(sys.executable), "src")
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


_IMAGE_DIR   = _resource_path("image_search")
_REF_W, _REF_H = 1920, 1080

_EDGE_MATCH_IMAGES: "set[str]" = set()

_MASK_MATCH_IMAGES: "set[str]" = {
    "42.플레이어나감인식.png",
    "41.미션종료.png",
}

_CHAR_IMAGES: "dict[str, str]" = {
    "검성":   "15.검성.png",
    "템플러": "16.템플러.png",
    "사냥꾼": "17.사냥꾼.png",
    "마도사": "18.마도사.png",
    "창술사": "19.창술사.png",
    "검객":   "20.검객.png",
}


@lru_cache(maxsize=64)
def _load_template(filename: str, screen_w: int, screen_h: int) -> "tuple | None":
    """스케일된 템플릿을 캐시. 해상도 변경 시 자동 무효화 (screen_w/h 키에 포함).
    반환: (tmpl_gray, tmpl_bgr, mask, nw, nh) 또는 None"""
    load_filename = filename
    if filename in _MASK_MATCH_IMAGES:
        base, ext = os.path.splitext(filename)
        masked_name = base + "_masked" + ext
        if os.path.isfile(os.path.join(_IMAGE_DIR, masked_name)):
            load_filename = masked_name

    path = os.path.join(_IMAGE_DIR, load_filename)
    if not os.path.exists(path):
        return None

    buf      = np.fromfile(path, dtype=np.uint8)
    tmpl_raw = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    if tmpl_raw is None:
        return None

    if tmpl_raw.ndim == 2:
        tmpl_gray = tmpl_raw
        tmpl_bgr  = cv2.cvtColor(tmpl_raw, cv2.COLOR_GRAY2BGR)
        mask      = None
    elif tmpl_raw.shape[2] == 4:
        tmpl_gray = cv2.cvtColor(tmpl_raw, cv2.COLOR_BGRA2GRAY)
        tmpl_bgr  = tmpl_raw[:, :, :3]
        mask      = tmpl_raw[:, :, 3]
    else:
        tmpl_gray = cv2.cvtColor(tmpl_raw, cv2.COLOR_BGR2GRAY)
        tmpl_bgr  = tmpl_raw
        mask      = None

    th, tw = tmpl_gray.shape
    nw = max(1, int(tw * screen_w / _REF_W))
    nh = max(1, int(th * screen_h / _REF_H))
    if (nw, nh) != (tw, th):
        tmpl_gray = cv2.resize(tmpl_gray, (nw, nh), interpolation=cv2.INTER_AREA)
        tmpl_bgr  = cv2.resize(tmpl_bgr,  (nw, nh), interpolation=cv2.INTER_AREA)
        if mask is not None:
            mask = cv2.resize(mask, (nw, nh), interpolation=cv2.INTER_NEAREST)

    return (tmpl_gray, tmpl_bgr, mask, nw, nh)


def _image_match(
    filename: str,
    threshold: float = 0.8,
    background: bool = False,
    edges: bool = False,
) -> "tuple[bool, float, tuple | None, tuple]":
    """(matched, confidence, coords|None, (nw, nh)) 반환."""
    edges = edges or (filename in _EDGE_MATCH_IMAGES)

    # 마스크 있으면 컬러 캡처로 결정 (템플릿 로드 전에 스크린 먼저 캡처하여 해상도 확인)
    # 임시 그레이 캡처로 해상도 확인
    _tmp = _capture_war3_gray_background() if background else _capture_war3_gray()
    if _tmp is None:
        return (False, -1.0, None, (0, 0))
    sh, sw = _tmp.shape[:2]

    tmpl_data = _load_template(filename, sw, sh)
    if tmpl_data is None:
        return (False, 0.0, None, (0, 0))

    tmpl_gray, tmpl_bgr, mask, nw, nh = tmpl_data
    use_color = (mask is not None) and (not edges)

    if use_color:
        screen = _capture_war3_bgr_background() if background else _capture_war3_bgr()
    else:
        screen = _tmp
    if screen is None:
        return (False, -1.0, None, (0, 0))

    if tmpl_gray.shape[0] > sh or tmpl_gray.shape[1] > sw:
        return (False, 0.0, None, (nw, nh))

    # ── 엣지 매칭 ──
    if edges:
        screen_g = screen if screen.ndim == 2 else cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        result   = cv2.matchTemplate(
            cv2.Canny(screen_g, 80, 200), cv2.Canny(tmpl_gray, 80, 200),
            cv2.TM_CCOEFF_NORMED
        )
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= threshold:
            return (True, max_val, (max_loc[0] + nw // 2, max_loc[1] + nh // 2), (nw, nh))
        return (False, max_val, None, (nw, nh))

    # ── 알파 마스크 매칭 ──
    if mask is not None:
        result  = cv2.matchTemplate(screen, tmpl_bgr, cv2.TM_SQDIFF, mask=mask)
        min_val, _, min_loc, _ = cv2.minMaxLoc(result)
        n_px    = max(1, int(np.sum(mask > 0)))
        confidence = max(0.0, 1.0 - (min_val / (n_px * 4800.0)))
        if confidence >= threshold:
            return (True, confidence, (min_loc[0] + nw // 2, min_loc[1] + nh // 2), (nw, nh))
        return (False, confidence, None, (nw, nh))

    # ── 기본 그레이 매칭 ──
    result = cv2.matchTemplate(screen, tmpl_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= threshold:
        return (True, max_val, (max_loc[0] + nw // 2, max_loc[1] + nh // 2), (nw, nh))
    return (False, max_val, None, (nw, nh))


def image_search(filename: str, threshold: float = 0.8) -> "tuple[int, int] | None":
    matched, _, coords, _ = _image_match(filename, threshold)
    return coords if matched else None


def image_exists(filename: str, threshold: float = 0.8,
                 background: bool = False) -> bool:
    matched, _, _, _ = _image_match(filename, threshold, background=background)
    return matched
