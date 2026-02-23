"""
utils/ocr.py — OCR 유틸리티 (Tesseract)
"""
import os
import sys

import cv2
import numpy as np
import pytesseract
from PIL import ImageGrab, Image


# ── Tesseract 경로 초기화 ────────────────────────────────────────────────────
def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)   # exe 옆 폴더
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_TESS_PATHS = [
    os.path.join(_base_dir(), "Tesseract-OCR", "tesseract.exe"),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _apply_tess_path(tp: str):
    """tesseract_cmd + TESSDATA_PREFIX + PATH 를 한 번에 설정."""
    pytesseract.pytesseract.tesseract_cmd = tp
    tess_dir = os.path.dirname(tp)
    tessdata_dir = os.path.join(tess_dir, "tessdata")
    os.environ["TESSDATA_PREFIX"] = tessdata_dir if os.path.isdir(tessdata_dir) else tess_dir
    # exe 환경에서 tesseract 서브프로세스가 DLL을 찾을 수 있도록 PATH에도 추가
    path_env = os.environ.get("PATH", "")
    if tess_dir.lower() not in path_env.lower():
        os.environ["PATH"] = tess_dir + os.pathsep + path_env


for _tp in _TESS_PATHS:
    if os.path.isfile(_tp):
        _apply_tess_path(_tp)
        break


def _ensure_tesseract():
    """OCR 호출 직전 tesseract_cmd 유효성 재확인 (exe 환경 방어용)."""
    cmd = pytesseract.pytesseract.tesseract_cmd
    if cmd and os.path.isfile(cmd):
        return
    for _tp in _TESS_PATHS:
        if os.path.isfile(_tp):
            _apply_tess_path(_tp)
            break

# 사냥반경 OCR 하드코딩 스크린 좌표
_HUNT_RADIUS_FHD_BBOX = (440, 340, 487, 364)   # FHD 풀스크린
_HUNT_RADIUS_WIN_BBOX = (758, 508, 809, 536)   # 창모드


def _best_contrast_channel(img: np.ndarray) -> np.ndarray:
    """BGRA/BGR → 대비(std)가 가장 높은 단일 채널 반환."""
    if img.ndim == 2:
        return img
    channels = [img[:, :, i] for i in range(min(3, img.shape[2]))]
    return max(channels, key=lambda c: float(c.std()))


def _ocr_preprocess(img: np.ndarray) -> Image.Image:
    """공통 OCR 전처리: 최고 대비 채널 → 3x LANCZOS4 → GaussianBlur → OTSU 이진화"""
    gray = _best_contrast_channel(img)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_LANCZOS4)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return Image.fromarray(thresh)


def _kor_available() -> bool:
    """kor.traineddata 번들 여부 확인"""
    # 초기화 루프가 성공한 경우
    tess_cmd = pytesseract.pytesseract.tesseract_cmd
    if tess_cmd and os.path.isfile(tess_cmd):
        tessdata = os.path.join(os.path.dirname(tess_cmd), "tessdata")
        return os.path.isfile(os.path.join(tessdata, "kor.traineddata"))
    # 초기화 루프가 실패한 경우 — 알려진 경로를 직접 확인
    for _tp in _TESS_PATHS:
        if os.path.isfile(_tp):
            tessdata = os.path.join(os.path.dirname(_tp), "tessdata")
            return os.path.isfile(os.path.join(tessdata, "kor.traineddata"))
    return False


def _ocr_hunt_radius() -> "tuple[int | None, str]":
    """사냥반경 숫자를 OCR로 읽어 (숫자|None, 디버그메시지) 반환."""
    from src.core.capture import _capture_war3_gray_background

    _ensure_tesseract()
    try:
        # 해상도와 무관하게 WC3 창을 직접 캡처 후 FHD 기준 좌표를 비율 스케일
        full = _capture_war3_gray_background()
        if full is None:
            return None, "PrintWindow 캡처 실패"
        cap_h, cap_w = full.shape[:2]
        sx, sy = cap_w / 1920.0, cap_h / 1080.0
        fx1, fy1, fx2, fy2 = _HUNT_RADIUS_FHD_BBOX
        x1 = int(fx1 * sx); y1 = int(fy1 * sy)
        x2 = int(fx2 * sx); y2 = int(fy2 * sy)
        gray = full[y1:y2, x1:x2]
        if gray.size == 0:
            return None, f"크롭 영역 비어있음 scaled=({x1},{y1},{x2},{y2}) cap={cap_w}×{cap_h}"

        pil_img = _ocr_preprocess(gray)
        text = pytesseract.image_to_string(
            pil_img,
            config="--psm 7 --oem 1 -c tessedit_char_whitelist=0123456789").strip()
        dbg = f"{cap_w}×{cap_h} scaled=({x1},{y1},{x2},{y2}) raw='{text}'"
        return (int(text) if text.isdigit() else None), dbg
    except Exception as e:
        return None, f"예외: {e}"


# public alias
ocr_hunt_radius = _ocr_hunt_radius


def ocr_text(
    img: np.ndarray,
    lang: str = "kor+eng",
    psm: int = 7,
) -> "tuple[str, str]":
    """한글+숫자(또는 지정 lang) OCR. 반환: (인식결과, 디버그메시지)"""
    import re as _re
    _ensure_tesseract()
    try:
        if lang.startswith("kor") and not _kor_available():
            return "", "kor.traineddata 없음 — eng 폴백"
        pil_img = _ocr_preprocess(img)
        cfg = f"--psm {psm} --oem 1"
        text = pytesseract.image_to_string(pil_img, lang=lang, config=cfg).strip()
        text = _re.sub(r"[^\uAC00-\uD7A30-9A-Za-z\s]", "", text)
        text = _re.sub(r"(?<=[\uAC00-\uD7A3])\s+(?=[\uAC00-\uD7A3])", "", text)
        text = _re.sub(r"\s+", " ", text).strip()
        return text, f"lang={lang} psm={psm} raw='{text}'"
    except Exception as e:
        return "", f"예외: {e}"
