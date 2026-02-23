"""
utils/updater.py — GitHub Releases 자동 업데이트 (타임스탬프 기반)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

GITHUB_OWNER = "PyFlowRPA"
GITHUB_REPO  = "PyNOX"
_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


def _exe_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_local_timestamp() -> str:
    """마지막 업데이트 시각 (ISO 8601). 파일 없으면 빈 문자열."""
    try:
        ts_path = os.path.join(_exe_dir(), "src", "last_update.txt")
        with open(ts_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def get_local_version() -> str:
    """src/version.py 의 __version__ (UI 표시용). 없으면 '?'."""
    try:
        ver_path = os.path.join(_exe_dir(), "src", "version.py")
        with open(ver_path, "r", encoding="utf-8") as f:
            m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', f.read(), re.MULTILINE)
        return m.group(1) if m else "?"
    except Exception:
        return "?"


def fetch_latest_release() -> "tuple[str, str, str, str]":
    """(태그, 다운로드URL, 릴리즈노트, published_at). 실패 시 ('','','','')"""
    try:
        req = urllib.request.Request(
            _API_URL,
            headers={"User-Agent": "PyNOX-Updater/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        tag          = data.get("tag_name", "").lstrip("v")
        notes        = data.get("body", "")
        published_at = data.get("published_at", "")  # e.g. "2026-02-23T10:30:00Z"
        url = ""
        for asset in data.get("assets", []):
            if asset.get("name", "").lower().endswith(".zip"):
                url = asset.get("browser_download_url", "")
                break
        return tag, url, notes, published_at
    except Exception:
        return "", "", "", ""


def needs_update(local_ts: str, remote_ts: str) -> bool:
    """remote_ts 가 local_ts 보다 최신이면 True.
    ISO 8601 문자열은 사전순 = 시간순이라 그냥 비교 가능.
    local_ts 가 없으면 (첫 설치) 항상 True.
    """
    if not remote_ts:
        return False
    if not local_ts:
        return True
    return remote_ts > local_ts


def download_and_extract(url: str, on_progress=None) -> str:
    """zip 다운로드 → %TEMP% 에 압축 해제 → zip 즉시 삭제 → 압축 해제 폴더 경로 반환."""
    import tempfile
    tmp = tempfile.gettempdir()
    dest_zip = os.path.join(tmp, "pynox_update.zip")

    req = urllib.request.Request(url, headers={"User-Agent": "PyNOX-Updater/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(dest_zip, "wb") as f:
            while True:
                buf = resp.read(65536)
                if not buf:
                    break
                f.write(buf)
                downloaded += len(buf)
                if on_progress and total:
                    on_progress(downloaded, total)

    extract_dir = os.path.join(tmp, "pynox_update_files")
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    with zipfile.ZipFile(dest_zip, "r") as z:
        z.extractall(extract_dir)
    os.remove(dest_zip)
    return extract_dir


def apply_update(extract_dir: str, published_at: str):
    """last_update.txt 삽입 → bat 생성 후 실행 → 현재 프로세스 종료.

    ZIP 안에 포함된 항목만 각 경로에 명시적으로 복사:
      src/          → base/src/
      _internal/    → base/_internal/
      PyNOX.exe     → base/PyNOX.exe
      wc3_config.json → base/wc3_config.json
    """
    src_in_zip = os.path.join(extract_dir, "src")

    # published_at 을 src/last_update.txt 로 미리 기록
    os.makedirs(src_in_zip, exist_ok=True)
    with open(os.path.join(src_in_zip, "last_update.txt"), "w", encoding="utf-8") as f:
        f.write(published_at)

    base     = _exe_dir()
    exe_name = os.path.basename(sys.executable) if getattr(sys, "frozen", False) else "PyNOX.exe"
    exe_path = os.path.join(base, exe_name)
    bat_path = os.path.join(base, "_updater.bat")

    dest_src      = os.path.join(base, "src")
    dest_internal = os.path.join(base, "_internal")
    dest_config   = os.path.join(base, "wc3_config.json")

    src_internal = os.path.join(extract_dir, "_internal")
    src_exe      = os.path.join(extract_dir, "PyNOX.exe")
    src_config   = os.path.join(extract_dir, "wc3_config.json")

    lines = [
        "@echo off",
        "chcp 949 > nul",
        "echo PyNOX 업데이트 적용 중...",
        "timeout /t 2 /nobreak > nul",
        # src/ → base/src/
        f"if exist \"{src_in_zip}\\\" xcopy /E /Y /I \"{src_in_zip}\\*\" \"{dest_src}\\\"",
        # _internal/ → base/_internal/
        f"if exist \"{src_internal}\\\" xcopy /E /Y /I \"{src_internal}\\*\" \"{dest_internal}\\\"",
        # PyNOX.exe → base/PyNOX.exe
        f"if exist \"{src_exe}\" copy /Y \"{src_exe}\" \"{exe_path}\"",
        # wc3_config.json → base/wc3_config.json
        f"if exist \"{src_config}\" copy /Y \"{src_config}\" \"{dest_config}\"",
        f"rmdir /S /Q \"{extract_dir}\"",
        "del \"%~f0\"",
        f"start \"\" \"{exe_path}\"",
    ]
    bat = "\n".join(lines) + "\n"
    with open(bat_path, "w", encoding="cp949") as f:
        f.write(bat)

    subprocess.Popen(
        ["cmd", "/c", bat_path],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
