"""
utils/crypto.py — 비밀번호 암호화/복호화 (XOR + Base64)
"""
import base64

_XOR_KEY = 0x5A


def encrypt_password(pw: str) -> str:
    xored = bytes(c ^ _XOR_KEY for c in pw.encode("utf-8"))
    return base64.b64encode(xored).decode("ascii")


def decrypt_password(enc: str) -> str:
    if not enc:
        return ""
    try:
        xored = base64.b64decode(enc.encode("ascii"))
        return bytes(c ^ _XOR_KEY for c in xored).decode("utf-8")
    except Exception:
        return ""
