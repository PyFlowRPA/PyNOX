"""
utils/config.py — 설정 파일 로드/저장 (스레드 세이프 + 인메모리 캐시)
"""
import json
import os
import sys
import threading

_cfg_lock  = threading.Lock()
_cfg_cache: "dict | None" = None
_cfg_dirty = False


def _exe_dir() -> str:
    """EXE 옆 디렉토리 (설정 파일용 — 항상 EXE 위치)"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # 패키지 구조: src/utils/config.py → 부모 2단계가 프로젝트 루트
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resource_path(rel: str) -> str:
    """번들 리소스 경로 (image_search, assets — exe 옆 src/ 폴더 기준)"""
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.dirname(sys.executable), "src")
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


CONFIG_FILE = os.path.join(_exe_dir(), "wc3_config.json")


def load_config() -> dict:
    """설정 파일 읽기 (캐시 활용). 파일이 없으면 빈 dict 반환."""
    global _cfg_cache
    with _cfg_lock:
        if _cfg_cache is not None:
            return dict(_cfg_cache)
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    _cfg_cache = json.load(f)
                    return dict(_cfg_cache)
            except Exception:
                pass
        _cfg_cache = {}
        return {}


def save_config(cfg: dict):
    """설정 파일 저장 (스레드 세이프, 캐시 동기화)."""
    global _cfg_cache
    with _cfg_lock:
        _cfg_cache = dict(cfg)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)


def update_config(key: str, value) -> None:
    """설정 단일 키 업데이트 후 저장."""
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)


def update_config_multi(updates: dict) -> None:
    """설정 다중 키 업데이트 후 저장."""
    cfg = load_config()
    cfg.update(updates)
    save_config(cfg)


def get_cfg(key: str, default=None):
    """현재 캐시에서 단일 키 읽기. 캐시 미초기화 시 파일에서 로드."""
    return load_config().get(key, default)


def invalidate_cache():
    """캐시를 강제 무효화 (다음 load_config() 에서 파일 재로드)."""
    global _cfg_cache
    with _cfg_lock:
        _cfg_cache = None
