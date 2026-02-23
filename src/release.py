"""
release.py — 버전 올리고 배포용 ZIP 생성
실행: py src/release.py
"""
import os
import re
import zipfile

_ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_PY  = os.path.join(_ROOT, "src", "version.py")
OUTPUT_ZIP  = os.path.join(_ROOT, "release.zip")
PACK_DIRS    = ["src"]
PACK_FILES   = []
IGNORE_DIRS  = {"__pycache__", "updater"}
IGNORE_FILES = {"build.py", "release.py"}   # 개발자 전용, 배포 불필요
IGNORE_EXTS  = {".pyc"}


def _read_version() -> str:
    with open(VERSION_PY, "r", encoding="utf-8") as f:
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', f.read(), re.MULTILINE)
    return m.group(1) if m else "0.0.0"


def _write_version(ver: str):
    with open(VERSION_PY, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(
        r'^(__version__\s*=\s*)["\'][^"\']+["\']',
        rf'\g<1>"{ver}"',
        content, flags=re.MULTILINE,
    )
    with open(VERSION_PY, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    os.chdir(_ROOT)
    print("=" * 40)
    print("  PyNOX 릴리즈 생성기")
    print("=" * 40)

    cur = _read_version()
    print(f"\n현재 버전: {cur}")
    new = input("새 버전 입력 (엔터 = 그대로): ").strip() or cur

    if new != cur:
        _write_version(new)
        print(f"  version.py → {new}")

    # ZIP 생성
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in PACK_DIRS:
            for root, dirs, files in os.walk(d):
                dirs[:] = [x for x in dirs if x not in IGNORE_DIRS]
                for fname in files:
                    if os.path.splitext(fname)[1] in IGNORE_EXTS:
                        continue
                    if fname in IGNORE_FILES:
                        continue
                    path = os.path.join(root, fname)
                    zf.write(path)

    size_kb = os.path.getsize(OUTPUT_ZIP) / 1024
    print(f"\n[완료] release.zip 생성됨  ({size_kb:.1f} KB)")
    print(f"\n다음 단계:")
    print(f"  1. GitHub → Releases → Draft a new release")
    print(f"  2. Tag: v{new}")
    print(f"  3. release.zip 첨부 후 Publish")


if __name__ == "__main__":
    main()
