# -*- mode: python ; coding: utf-8 -*-
# PyNOX.spec — PyInstaller 빌드 설정
# src/ 는 외부 파일로 유지 (업데이트 패치 대상) → exe 에 포함하지 않음

import os

block_cipher = None

# ── 사용하지 않는 Qt 모듈 제외 (용량 절약) ──────────────────────────────
_QT_EXCLUDES = [
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
    "PySide6.QtBluetooth", "PySide6.QtCharts", "PySide6.QtConcurrent",
    "PySide6.QtDataVisualization", "PySide6.QtDBus", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtLocation", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtNetwork", "PySide6.QtNetworkAuth",
    "PySide6.QtNfc", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtPositioning",
    "PySide6.QtPrintSupport", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtQuick3D", "PySide6.QtQuickControls2", "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
    "PySide6.QtSerialBus", "PySide6.QtSerialPort", "PySide6.QtSpatialAudio",
    "PySide6.QtSql", "PySide6.QtStateMachine", "PySide6.QtSvg",
    "PySide6.QtSvgWidgets", "PySide6.QtTest", "PySide6.QtUiTools",
    "PySide6.QtWebChannel", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets", "PySide6.QtXml",
]

# ── src/ 및 불필요한 stdlib 제외 ─────────────────────────────────────────
_EXCLUDES = _QT_EXCLUDES + [
    # src/ 는 외부 디스크에서 로드
    "src", "src.core", "src.macro", "src.ui", "src.utils",
    # 사용 안 하는 stdlib
    "tkinter", "turtle", "unittest", "pydoc", "doctest",
    "xmlrpc", "ftplib", "imaplib", "poplib", "smtplib",
    "http.server",
    # 대형 패키지
    "matplotlib", "scipy", "pandas",
]

icon_file = "icon.ico" if os.path.exists("icon.ico") else None

a = Analysis(
    ["PyNOX.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[
        # OpenCV / 이미지 처리
        "cv2",
        "numpy",
        "numpy.core._multiarray_umath",
        "PIL.Image",
        "PIL.ImageGrab",
        "PIL._imaging",
        "mss",
        "mss.windows",
        # Windows API
        "win32api",
        "win32con",
        "win32gui",
        "win32ui",
        "win32process",
        "pywintypes",
        # 게임 메모리
        "pymem",
        "pymem.process",
        # OCR
        "pytesseract",
        # 프로세스
        "psutil",
        "psutil._pswindows",
        # 키보드 후킹
        "pynput",
        "pynput.keyboard",
        "pynput._util.win32",
        # numpy.random 의존
        "secrets",
        # HTTP 요청 (녹스 맵 다운로드)
        "requests",
        "requests.adapters",
        "requests.auth",
        "requests.cookies",
        "requests.exceptions",
        "requests.models",
        "requests.sessions",
        "requests.utils",
        "urllib3",
        "urllib3.util.retry",
        "certifi",
        "charset_normalizer",
        "idna",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PyNOX",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python3*.dll"],
    console=False,          # GUI 앱 → 콘솔 창 없음
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
    uac_admin=True,         # 관리자 권한 요청 (매니페스트)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python3*.dll"],
    name="PyNOX",
)
