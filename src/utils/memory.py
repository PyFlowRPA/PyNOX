"""
utils/memory.py — PyMem 게임 메모리 패치 유틸
"""
import ctypes
import os
import stat
import struct as _struct
import time as _time
import winreg

import pymem
import pymem.process


_DELAY_PATTERN = bytes([0xC0, 0xD6, 0xDB, 0x68, 0xC0])

# ── 채팅 EditBox 패턴 (OpenCirnix Message.cs 기준) ─────────────────────────────
_CHAT_PATTERN = bytes([0x94, 0x28, 0x49, 0x65, 0x94])
_HIDE_PATTERN = bytes([0xB0, 0x32, 0x5B, 0x2C, 0xB0])
_chat_edit_box_cache: "int | None" = None   # storm_base + 0x58280 체인 (안정적, 캐시)
_storm_base_cache: "int | None" = None
_game_base_cache:  "int | None" = None


def _bring(pm, addr: int, size: int) -> "bytes | None":
    """OpenCirnix Bring() 재현: VirtualProtectEx(0x40) → ReadProcessMemory → 복원.
    실행 전용(PAGE_EXECUTE) 등 보호된 메모리 노드도 읽을 수 있도록 보호 변경."""
    kernel32 = ctypes.windll.kernel32
    old = ctypes.c_ulong(0)
    kernel32.VirtualProtectEx(pm.process_handle, ctypes.c_void_p(addr),
                               size, 0x40, ctypes.byref(old))
    try:
        buf = pm.read_bytes(addr, size)
    except Exception:
        buf = None
    kernel32.VirtualProtectEx(pm.process_handle, ctypes.c_void_p(addr),
                               size, old, ctypes.byref(ctypes.c_ulong(0)))
    return buf


def _follow_pointer(pm, offset: int, signature: bytes) -> "int | None":
    """OpenCirnix FollowPointer() 재현: offset에서 4바이트 역참조 후 시그니처 체인 탐색."""
    buf = _bring(pm, offset, 4)
    if not buf:
        return None
    ptr = int.from_bytes(buf, "little")
    for _ in range(2000):
        if ptr == 0:
            return None
        data = _bring(pm, ptr, 4 + len(signature))
        if not data:
            return None
        if data[4:4 + len(signature)] == signature:
            return ptr
        ptr = int.from_bytes(data[:4], "little")
    return None


def _find_hide_offset(pm, storm_base: int) -> "int | None":
    """OpenCirnix GetTargetReceiveStatus() — 매 호출마다 체인 재탐색 (주소 동적 변경)."""
    node = _follow_pointer(pm, storm_base + 0x582F0, _HIDE_PATTERN)
    if node is None:
        return None
    target = node + 0x2A8
    # DirectBring 검증 (OpenCirnix와 동일)
    if _bring(pm, target, 4) is None:
        return None
    return target


def send_chat_memory(hwnd: int, text: str, hide: bool = False) -> "tuple[bool, str]":
    """WC3 채팅 EditBox에 WriteProcessMemory로 직접 UTF-8 텍스트 쓰기 후 Enter 전송.
    hide=True 시 OpenCirnix MessageHide() 방식으로 채팅창 UI를 숨기고 전송."""
    global _chat_edit_box_cache, _storm_base_cache, _game_base_cache
    user32 = ctypes.windll.user32
    pm = None
    try:
        pm = pymem.Pymem("War3.exe")

        # 모듈 베이스 캐시 (storm + game 동시)
        if _storm_base_cache is None or _game_base_cache is None:
            for mod in pymem.process.enum_process_module(pm.process_handle):
                name = os.path.basename(mod.name).lower()
                if name == "storm.dll":
                    _storm_base_cache = int(mod.lpBaseOfDll)
                elif name == "game.dll":
                    _game_base_cache = int(mod.lpBaseOfDll)
        if _storm_base_cache is None:
            return False, "[채팅] storm.dll 미발견"

        # EditBox 캐시 탐색 (_follow_pointer 사용)
        if _chat_edit_box_cache is None:
            node = _follow_pointer(pm, _storm_base_cache + 0x58280, _CHAT_PATTERN)
            if node is None:
                return False, "[채팅] EditBox 패턴 미발견"
            _chat_edit_box_cache = node

        # OpenCirnix ApplyChat(TryHide) 흐름 재현:
        # 채팅창 열기 → hide 선적용(flash 최소화) → 50ms 대기 → 텍스트 기록 → MessageHide() → 전송
        def _is_chat_open():
            if _game_base_cache is None:
                return False
            try:
                return bool(pm.read_int(_game_base_cache + 0xD04FEC))
            except Exception:
                return False

        if not _is_chat_open():
            user32.PostMessageW(hwnd, 0x100, 13, 0)
            user32.PostMessageW(hwnd, 0x101, 13, 0)
            if hide:
                # 채팅창 렌더링 전에 선제적으로 hide 적용 → 화면 노출 최소화
                _pre = _find_hide_offset(pm, _storm_base_cache)
                if _pre is not None:
                    pm.write_bytes(_pre, bytes([0x7F, 0, 0, 0]), 4)
            # WC3가 채팅창을 열고 히스토리로 EditBox를 초기화할 때까지 대기
            # hide 여부와 무관하게 반드시 필요 — 없으면 히스토리에 덮어씌워짐
            _time.sleep(0.05)

        # 텍스트를 버퍼에 직접 기록
        # ★ 반드시 채팅창 open + 50ms 대기 이후에 써야 함:
        #   WC3는 채팅창을 열 때 마지막 커맨드 히스토리로 EditBox를 덮어쓰는데,
        #   open 전에 쓰면 그 히스토리에 덮어쓰여 엉뚱한 텍스트가 전송된다.
        msg_offset = _chat_edit_box_cache + 0x88
        encoded = text.encode("utf-8") + b"\x00"
        pm.write_bytes(msg_offset, encoded, len(encoded))

        if hide:
            # 주소가 동적으로 변경되므로 전송 직전에 재탐색 후 재적용
            hide_offset = _find_hide_offset(pm, _storm_base_cache)
            if hide_offset is not None:
                pm.write_bytes(hide_offset, bytes([0x7F, 0, 0, 0]), 4)

        user32.PostMessageW(hwnd, 0x100, 13, 0)
        user32.PostMessageW(hwnd, 0x101, 13, 0)
        _time.sleep(0.05)

        # 전송 후에도 채팅창이 열려있으면 강제 닫기 (hide 재적용 후 Enter)
        if _is_chat_open():
            if hide:
                hide_offset2 = _find_hide_offset(pm, _storm_base_cache)
                if hide_offset2 is not None:
                    pm.write_bytes(hide_offset2, bytes([0x7F, 0, 0, 0]), 4)
            user32.PostMessageW(hwnd, 0x100, 13, 0)
            user32.PostMessageW(hwnd, 0x101, 13, 0)

        return True, f"채팅 전송: {text}"
    except Exception as e:
        _chat_edit_box_cache = None
        _storm_base_cache = None
        _game_base_cache = None
        return False, f"[채팅] 전송 실패: {e}"
    finally:
        if pm is not None:
            try:
                pm.close_process()
            except Exception:
                pass

_WAR3_PREF_PATH = os.path.join(
    os.path.expandvars("%USERPROFILE%"),
    "Documents", "Warcraft III", "War3Preferences.txt"
)

_WC3_VIDEO_REG = r"Software\Blizzard Entertainment\Warcraft III\Video"


def _mem_patch(pm, addr: int, data: bytes):
    """VirtualProtectEx → WriteProcessMemory → 복원."""
    kernel32 = ctypes.windll.kernel32
    old = ctypes.c_ulong(0)
    kernel32.VirtualProtectEx(pm.process_handle, ctypes.c_void_p(addr),
                               len(data), 0x40, ctypes.byref(old))
    pm.write_bytes(addr, data, len(data))
    kernel32.VirtualProtectEx(pm.process_handle, ctypes.c_void_p(addr),
                               len(data), old, ctypes.byref(ctypes.c_ulong(0)))


def write_game_delay(delay: int) -> "tuple[bool, str]":
    """딜레이 값을 WC3 메모리에 직접 쓰기. (ok, 메시지) 반환."""
    if not (0 <= delay <= 550):
        return False, f"[경고] 딜레이 범위 오류: {delay} (0~550)"
    pm = None
    try:
        pm = pymem.Pymem("War3.exe")
        storm_base = None
        for mod in pymem.process.enum_process_module(pm.process_handle):
            if os.path.basename(mod.name).lower() == "storm.dll":
                storm_base = int(mod.lpBaseOfDll)
                break
        if storm_base is None:
            return False, "[경고] storm.dll 을 찾을 수 없습니다."

        ptr = pm.read_uint(storm_base + 0x58330)
        if ptr == 0:
            return False, "[경고] 딜레이 포인터 체인 시작점이 0"

        offset = None
        for _ in range(2000):
            try:
                data = pm.read_bytes(ptr, 4 + len(_DELAY_PATTERN))
            except Exception:
                break
            if data[4:4 + len(_DELAY_PATTERN)] == _DELAY_PATTERN:
                offset = ptr
                break
            next_ptr = int.from_bytes(data[:4], "little")
            if next_ptr == 0:
                break
            ptr = next_ptr

        if offset is None:
            return False, "[경고] 딜레이 패턴을 찾지 못했습니다."

        delay_base = offset + 0x2F0
        delay_bytes = delay.to_bytes(4, "little")
        for i in [0, 0x220, 0x440]:
            for j in [0, 4]:
                _mem_patch(pm, delay_base + i + j, delay_bytes)

        return True, f"딜레이 직접 적용 완료: {delay}ms"
    except Exception as e:
        return False, f"[오류] 딜레이 설정 실패: {e}"
    finally:
        if pm is not None:
            try:
                pm.close_process()
            except Exception:
                pass


def write_start_speed_zero() -> "tuple[bool, str]":
    """StartDelay 를 0.01f 로 설정 (항상 0). (ok, 메시지) 반환."""
    pm = None
    try:
        pm = pymem.Pymem("War3.exe")
        game_base = None
        for mod in pymem.process.enum_process_module(pm.process_handle):
            if os.path.basename(mod.name).lower() == "game.dll":
                game_base = int(mod.lpBaseOfDll)
                break
        if game_base is None:
            return False, "[경고] game.dll 을 찾을 수 없습니다."

        _mem_patch(pm, game_base + 0x324146, _struct.pack("<f", 0.01))
        return True, "시작속도 0 설정 완료 (!ss 0)"
    except Exception as e:
        return False, f"[오류] 시작속도 설정 실패: {e}"
    finally:
        if pm is not None:
            try:
                pm.close_process()
            except Exception:
                pass


def _set_pref_writable():
    """War3Preferences.txt 를 쓰기 가능으로 변경."""
    try:
        if os.path.isfile(_WAR3_PREF_PATH):
            os.chmod(_WAR3_PREF_PATH, stat.S_IREAD | stat.S_IWRITE)
    except Exception:
        pass


def _set_pref_readonly():
    """War3Preferences.txt 를 읽기 전용으로 변경 (JNLoader 덮어쓰기 방지)."""
    try:
        if os.path.isfile(_WAR3_PREF_PATH):
            os.chmod(_WAR3_PREF_PATH, stat.S_IREAD)
    except Exception:
        pass


def patch_war3_preferences(is_fhd: bool) -> "tuple[bool, str]":
    """War3Preferences.txt 를 모니터 해상도에 맞게 수정 후 읽기 전용으로 잠금."""
    from src.utils.config import load_config
    if not os.path.isfile(_WAR3_PREF_PATH):
        return False, f"War3Preferences.txt 없음: {_WAR3_PREF_PATH}"
    try:
        _set_pref_writable()
        with open(_WAR3_PREF_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if is_fhd:
            patches = {"windowmode": "0", "reswidth": "1920", "resheight": "1080"}
            mode_str = "풀스크린 1920×1080 (FHD)"
        else:
            cfg = load_config()
            wmode = cfg.get("wc3_window_mode", "fullscreen")
            if wmode == "fullscreen":
                patches = {"windowmode": "0", "reswidth": "1920", "resheight": "1080"}
                mode_str = "풀스크린 1920×1080 (FHD 초과)"
            else:
                patches = {"windowmode": "1", "windowwidth": "1920", "windowheight": "1080"}
                mode_str = "창모드 1920×1080 (FHD 초과)"
        new_lines = []
        for line in lines:
            key_part = line.split("=")[0].strip().lower()
            if key_part in patches:
                new_lines.append(f"{key_part}={patches[key_part]}\n")
            else:
                new_lines.append(line)
        with open(_WAR3_PREF_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        _set_pref_readonly()
        return True, f"War3Preferences.txt 패치 완료 → {mode_str} (읽기 전용 잠금)"
    except Exception as e:
        return False, f"War3Preferences.txt 패치 실패: {e}"


def patch_war3_resolution_registry() -> "tuple[bool, str]":
    """레지스트리 HKCU\\...\\Warcraft III\\Video 의 reswidth/resheight 를 1920×1080 으로 강제."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WC3_VIDEO_REG,
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "reswidth",  0, winreg.REG_DWORD, 1920)
            winreg.SetValueEx(key, "resheight", 0, winreg.REG_DWORD, 1080)
        return True, "레지스트리 클라이언트 해상도 1920×1080 적용 완료"
    except Exception as e:
        return False, f"레지스트리 해상도 패치 실패: {e}"
