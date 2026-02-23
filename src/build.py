"""
build.py — PyNOX exe 빌드 스크립트
실행: py src/build.py
"""
import os
import shutil
import subprocess
import sys
import time

_ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIST    = os.path.join(_ROOT, "dist", "PyNOX")        # 최종 배포 폴더
_DIST_TMP = os.path.join(_ROOT, "dist", "_build_tmp")  # PyInstaller 임시 출력
_SRC     = os.path.join(_ROOT, "src")

# 배포 폴더에 복사하지 않을 파일 (개발 도구)
_SRC_EXCLUDES = {"build.py", "release.py", "__pycache__"}


def _folder_size_mb(path: str) -> float:
    total = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, files in os.walk(path)
        for f in files
    )
    return total / 1024 / 1024


def _try_delete(path: str, retries: int = 3, delay: float = 2.0) -> bool:
    """rd /s /q 로 삭제 시도. 실패 시 재시도."""
    for i in range(retries):
        subprocess.run(["cmd", "/c", "rd", "/s", "/q", path],
                       check=False, capture_output=True)
        if not os.path.exists(path):
            return True
        if i < retries - 1:
            print(f"  삭제 대기 중... ({i+1}/{retries-1})")
            time.sleep(delay)
    return not os.path.exists(path)


def main():
    os.chdir(_ROOT)

    print("=" * 50)
    print("  PyNOX 빌드 시작")
    print("=" * 50)

    # ── 0. 임시 빌드 폴더 정리 ───────────────────────────
    if os.path.exists(_DIST_TMP):
        print("\n[0/4] 이전 임시 빌드 폴더 삭제 중...")
        if not _try_delete(_DIST_TMP):
            print("  [경고] 임시 폴더 삭제 실패 - 빌드 중단")
            sys.exit(1)
        print("  완료")

    # ── 1. PyInstaller 실행 (임시 경로로 출력) ────────────
    print("\n[1/4] PyInstaller 실행 중...")
    ret = subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "PyNOX.spec",
            "--clean",
            "--noconfirm",
            "--distpath", _DIST_TMP,
        ],
        cwd=_ROOT,
    )
    if ret.returncode != 0:
        print("\n[오류] PyInstaller 빌드 실패")
        sys.exit(1)

    _tmp_pynox = os.path.join(_DIST_TMP, "PyNOX")

    # ── 2. src/ 폴더 → 임시 빌드에 복사 ─────────────────
    print("\n[2/4] src/ 복사 중...")
    dst_src = os.path.join(_tmp_pynox, "src")
    if os.path.exists(dst_src):
        shutil.rmtree(dst_src)
    shutil.copytree(
        _SRC, dst_src,
        ignore=shutil.ignore_patterns(*_SRC_EXCLUDES),
    )

    # ── 3. 불필요한 DLL 제거 (용량 절감) ──────────────────
    print("\n[3/4] 불필요한 파일 정리 중...")
    _internal = os.path.join(_tmp_pynox, "_internal")
    _REMOVE_FILES = [
        # OpenCV 영상 I/O (이미지 매칭만 사용하므로 불필요)
        os.path.join(_internal, "cv2", "opencv_videoio_ffmpeg4100_64.dll"),
        os.path.join(_internal, "cv2", "opencv_videoio_ffmpeg460_64.dll"),
        # 소프트웨어 OpenGL 렌더러 (위젯 앱에서 불필요)
        os.path.join(_internal, "PySide6", "opengl32sw.dll"),
        # 제외했는데 슬립스루된 Qt 모듈
        os.path.join(_internal, "PySide6", "Qt6Quick.dll"),
        os.path.join(_internal, "PySide6", "Qt6Qml.dll"),
        os.path.join(_internal, "PySide6", "Qt6Pdf.dll"),
        os.path.join(_internal, "PySide6", "Qt6QmlModels.dll"),
        os.path.join(_internal, "PySide6", "Qt6QmlWorkerScript.dll"),
        os.path.join(_internal, "PySide6", "Qt6OpenGL.dll"),
        os.path.join(_internal, "PySide6", "Qt6Network.dll"),
    ]
    saved = 0
    for f in _REMOVE_FILES:
        if os.path.exists(f):
            saved += os.path.getsize(f)
            os.remove(f)
    print(f"  절감: {saved/1024/1024:.1f} MB")

    # 설정 파일 복사
    for fname in ["wc3_config.json"]:
        src_f = os.path.join(_ROOT, fname)
        if os.path.exists(src_f):
            shutil.copy2(src_f, _tmp_pynox)

    # ── 4. 최종 dist/PyNOX 로 반영 ───────────────────────
    print("\n[4/4] dist/PyNOX 업데이트 중...")
    os.makedirs(_DIST, exist_ok=True)

    # xcopy /E /Y /I: 파일 단위 덮어쓰기 (폴더 삭제 불필요)
    ret2 = subprocess.run(
        ["xcopy", f"{_tmp_pynox}\\*", f"{_DIST}\\",
         "/E", "/Y", "/I", "/Q"],
        cwd=_ROOT,
    )
    if ret2.returncode not in (0, 1):  # xcopy: 0=OK, 1=파일 없음도 정상
        print("  [경고] xcopy 일부 실패 (잠긴 파일 있을 수 있음)")

    # 임시 폴더 삭제
    _try_delete(_DIST_TMP)

    # ── 결과 출력 ─────────────────────────────────────────
    size = _folder_size_mb(_DIST)
    print(f"\n{'=' * 50}")
    print(f"  빌드 완료!")
    print(f"  경로: {_DIST}")
    print(f"  크기: {size:.1f} MB")
    print(f"{'=' * 50}")
    print("\n배포 구조:")
    print("  dist/PyNOX/")
    print("    PyNOX.exe        <- 실행 파일")
    print("    src/             <- 업데이트 패치 대상 (.py + 이미지)")
    print("    wc3_config.json  <- 유저 설정")


if __name__ == "__main__":
    main()
