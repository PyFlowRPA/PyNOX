"""
macro/worker.py — WatchWorker (QObject, PySide6)
"""
import ctypes
import ctypes.wintypes
import os
import sys
import random
import time
import threading

import psutil
import pymem
import pymem.process
import win32api

from PySide6.QtCore import QObject, Signal

from datetime import datetime
def now() -> str:
    return datetime.now().strftime("%H:%M:%S")

from src.utils.config import load_config, save_config
from src.utils.process import find_war3_hwnd
from src.utils.memory import write_game_delay, write_start_speed_zero, patch_war3_preferences, patch_war3_resolution_registry, send_chat_memory
from src.core.image_match import _image_match, image_exists, image_search, _CHAR_IMAGES
from src.constants import IMG
from src.core.input import (
    _user32, _press_vk, _send_key, click_image_center, right_click_image_center,
    move_cursor_to, _scale_coords, type_string, press_enter,
    _VK_RETURN, _VK_CONTROL, _VK_SHIFT, _VK_TAB, _VK_ESCAPE,
    _VK_C, _VK_G, _VK_V, _VK_S, _VK_LEFT, _VK_RIGHT,
    _KBD_INPUT, _KEYEVENTF_KEYUP, _KEYEVENTF_UNICODE,
    _PORTAL_COORDS,
)
from src.core.capture import _get_pixel_at_client
from src.ui.theme import TEXT, GREEN, RED, YELLOW

from src.utils.crypto import decrypt_password

# _IMAGE_DIR: 이미지 검색 폴더 경로 (템플릿 이미지)
_IMAGE_DIR = os.path.join(
    os.path.join(os.path.dirname(sys.executable), "src") if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "image_search",
)


class WatchWorker(QObject):
    log_signal     = Signal(str, str)        # 새 줄 추가
    update_signal  = Signal(str, str)        # 마지막 줄 덮어쓰기
    status_signal  = Signal(str, str)
    overlay_signal = Signal(int, int, int, int)  # cx, cy, tw, th (클라이언트 좌표)
    finished       = Signal()

    def __init__(self, ingame: bool = False):
        super().__init__()
        self._running            = False
        self._ingame             = ingame
        self._boss_priority_done = False  # 보스 우선 토벌 1회 사용 여부
        self._fm_blacklist: dict = {}     # 프리매치 블랙리스트 {방ID: 만료timestamp}

    def log(self, msg: str, level: str = "info"):
        self.log_signal.emit(f"[{now()}] {msg}", level)

    def update_log(self, msg: str, level: str = "info"):
        self.update_signal.emit(f"[{now()}] {msg}", level)

    def status(self, msg: str, color: str = TEXT):
        self.status_signal.emit(msg, color)

    def start(self):
        self._running = True
        try:
            self._run()
        except Exception as e:
            import traceback
            self.log_signal.emit(
                f"[{now()}] [치명적 오류] 워커 예외: {e}", "error")
            self.log_signal.emit(
                f"[{now()}] {traceback.format_exc()}", "error")
        finally:
            self._running = False
            self.finished.emit()

    def stop(self):
        self._running = False

    def _sleep(self, seconds: float, step: float = 0.1) -> bool:
        """`seconds` 동안 대기. 중지 요청 시 즉시 False 반환."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            if not self._running:
                return False
            remaining = min(step, deadline - time.time())
            if remaining > 0:
                time.sleep(remaining)
        return True

    # ── 흐름 ──────────────────────────────────────
    def _run(self):
        while self._running:
            if not self._ingame:
                # STEP 1: War3.exe 프로세스 대기
                self.log("War3.exe 프로세스 대기 중...")
                self.status("War3.exe 대기 중...", YELLOW)
                proc = self._wait_for_process("War3.exe", timeout=60)
                if proc is None:
                    self.log("[오류] War3.exe 프로세스를 찾지 못했습니다.", "error")
                    self.status("War3.exe 감지 실패", RED)
                    return
                self.log(f"War3.exe 감지! PID: {proc.pid}", "success")

                # STEP 2: WC3 창 대기
                self.log("WC3 창 대기 중...")
                self.status("WC3 창 대기 중...", YELLOW)
                hwnd = self._wait_for_hwnd(timeout=60)
                if hwnd is None:
                    self.log("[오류] WC3 창을 찾지 못했습니다.", "error")
                    self.status("WC3 창 감지 실패", RED)
                    return
                self.log(f"WC3 창 감지! (HWND: {hwnd})", "success")

                # STEP 3: 메인 화면 이미지 서치
                img = IMG.MAIN_SCREEN
                if not os.path.exists(os.path.join(_IMAGE_DIR, img)):
                    self.log(f"[경고] {img} 없음 → image_search 폴더에 템플릿을 추가하세요.", "warn")
                    self.status("템플릿 없음", RED)
                    return

                self.log(f"메인 화면 감지 대기 중... ({img})")
                self.status("메인 화면 대기 중...", YELLOW)
                ok, _ = self._wait_for_image(img, timeout=120, click=True)
                if not ok:
                    self.log("[경고] 메인 화면 감지 시간 초과 (120초)", "warn")
                    self.status("메인 화면 감지 실패", RED)
                    return
                self.log("메인 화면 감지 + 클릭 완료!", "success")
                if not self._running:
                    return

                # STEP 4: 로그인 루프
                self._login_loop()
                if not self._running:
                    return

            # STEP 5: 인게임 루틴 (로그인 완료 후 또는 인게임 바로시작 모드)
            self._run_ingame()
            if not self._running:
                return

            # 인게임 종료 후 → 다음 사이클은 War3.exe부터 전체 재시작
            self._ingame = False
            self.log("인게임 종료 → 전체 흐름 재시작 (War3.exe 대기)...", "info")
            self.status("재시작 대기 중...", YELLOW)

    # ── 자동사냥 설정 ──────────────────────────────────
    def _run_auto_hunt(self):
        """자동사냥 다이얼로그 열기 → 제자리사냥 ON/OFF 설정."""
        cfg = load_config()
        stay_hunt = cfg.get("stay_hunt", False)
        self.log("=== 자동사냥 설정 시작 ===", "info")
        self.status("자동사냥 설정 중...", YELLOW)

        # ── 13번 or 37번 동시 서치 → 우클릭 → 26번 다이얼로그 대기 루프 ──
        while self._running:
            found_event = threading.Event()
            result = [False, None]  # [ok, coords]

            def _search(filename):
                ok, coords = self._wait_for_image(filename, timeout=2, click=False, silent=True)
                if ok and not found_event.is_set():
                    result[0] = True; result[1] = coords
                    found_event.set()

            threads = [
                threading.Thread(target=_search, args=(IMG.LOADING_CURSOR,), daemon=True),
                threading.Thread(target=_search, args=(IMG.HUNT_ON_CHECK,),    daemon=True),
            ]
            for t in threads: t.start()
            found_event.wait(timeout=2.5)
            for t in threads: t.join(timeout=0)

            if not result[0]:
                self.log("[자동사냥] 13번/37번 미감지 → 재시도", "warn")
                continue
            coords13 = result[1]
            move_cursor_to(coords13[0], coords13[1])
            time.sleep(0.1)
            right_click_image_center(coords13[0], coords13[1])
            self.log("[자동사냥] 감지 → 우클릭", "info")

            ok26, _ = self._wait_for_image(
                IMG.HUNT_DIALOG, timeout=2, click=False)
            if ok26:
                self.log("[자동사냥] 다이얼로그 감지 → 설정 진행", "success")
                break
            self.log("[자동사냥] 다이얼로그 미감지 → 재시도", "warn")

        if not self._running:
            return

        # ── 제자리사냥 ON/OFF 설정 ──
        time.sleep(0.5)
        ok24, val24, coords24, _ = _image_match(IMG.HUNT_STAY,     threshold=0.75)
        ok27, val27, coords27, _ = _image_match(IMG.HUNT_STAY_OFF, threshold=0.85)
        self.log(f"[자동사냥] 24번 신뢰도={val24:.3f} coords={coords24} / 27번 신뢰도={val27:.3f} coords={coords27}", "info")
        # 둘 다 감지되면 신뢰도 높은 쪽만 채택
        if ok24 and ok27:
            if val24 >= val27:
                ok27 = False
            else:
                ok24 = False

        if stay_hunt:
            # 목표: 제자리사냥 ON → OFF 상태(27번)가 감지되면 클릭, 없으면 이미 ON
            if ok27 and coords27:
                self.log("[자동사냥] 제자리사냥 OFF 감지 → 클릭하여 ON으로 변경", "info")
                click_image_center(coords27[0], coords27[1])
            elif ok24:
                self.log("[자동사냥] 제자리사냥 이미 ON 상태", "info")
            else:
                self.log("[자동사냥] 제자리사냥 이미지 미감지", "warn")
        else:
            # 목표: 제자리사냥 OFF → ON 상태(24번)가 감지되면 클릭, 없으면 이미 OFF
            if ok24 and coords24:
                self.log("[자동사냥] 제자리사냥 ON 감지 → 클릭하여 OFF로 변경", "info")
                click_image_center(coords24[0], coords24[1])
            elif ok27:
                self.log("[자동사냥] 제자리사냥 이미 OFF 상태", "info")
            else:
                self.log("[자동사냥] 제자리사냥 이미지 미감지", "warn")

        # ── 사냥반경 조정 (OCR 불필요: 최솟값 리셋 후 목표값까지 증가) ──
        target_radius = load_config().get("hunt_radius", 1000)
        target_radius = max(500, min(3000, round(target_radius / 100) * 100))
        up_clicks = (target_radius - 500) // 100   # 500이 최솟값
        btn_minus = _scale_coords(420, 350)
        btn_plus  = _scale_coords(500, 350)
        self.log(f"[자동사냥] 사냥반경 조정 → 목표:{target_radius} (리셋 후 +{up_clicks}클릭)", "info")
        # 1) 최솟값(500)으로 리셋: 최대 범위(3000-500=2500, 25클릭) 이상 내림
        for _ in range(26):
            if not self._running: break
            click_image_center(btn_minus[0], btn_minus[1])
            time.sleep(0.08)
        # 2) 목표값까지 증가
        for _ in range(up_clicks):
            if not self._running: break
            click_image_center(btn_plus[0], btn_plus[1])
            time.sleep(0.08)
        self.log(f"[자동사냥] 사냥반경 설정 완료: {target_radius}", "success")

        # ── 확인 버튼 클릭 → 다이얼로그 닫힘 확인 ──
        self.log("[자동사냥] 확인 버튼 클릭", "info")
        ok28, _, coords28, _ = _image_match(IMG.HUNT_DIALOG_CONFIRM)
        if ok28 and coords28:
            click_image_center(coords28[0], coords28[1])
        else:
            self.log("[자동사냥] 확인 버튼 미감지", "warn")

        time.sleep(0.3)
        ok26_check, _, _, _ = _image_match(IMG.HUNT_DIALOG)
        if ok26_check:
            self.log("[자동사냥] 다이얼로그 미닫힘 → 확인 버튼 재클릭", "warn")
            ok28, _, coords28, _ = _image_match(IMG.HUNT_DIALOG_CONFIRM)
            if ok28 and coords28:
                click_image_center(coords28[0], coords28[1])
            else:
                self.log("[자동사냥] 확인 버튼 재감지 실패", "warn")
        else:
            self.log("[자동사냥] 다이얼로그 정상 닫힘", "success")

        self.log("=== 자동사냥 설정 완료 ===", "success")
        self.status("자동사냥 설정 완료!", GREEN)

    # ── 부대지정 루프 ──────────────────────────────────
    def _assign_control_groups(self):
        """좌표 클릭 → Ctrl+번호 부대지정 → 22번 이미지로 검증.
        영웅 선택 시 22번 감지, 창고 선택 시 22번 미감지이면 통과."""
        cfg          = load_config()
        hero_num     = cfg.get("hero_group", 1)
        storage_num  = cfg.get("storage_group", 2)
        hero_vk      = ord(str(hero_num))
        storage_vk   = ord(str(storage_num))

        _VK_9 = ord('9')
        _VK_0 = ord('0')
        self.log(f"부대지정 시작 (영웅:{hero_num}번+9번, 창고:{storage_num}번+0번)", "info")
        self.status("부대지정 중...", YELLOW)

        while self._running:
            hwnd = find_war3_hwnd()
            if hwnd:
                _user32.SetForegroundWindow(hwnd)
                deadline_fg = time.time() + 1.0
                while time.time() < deadline_fg:
                    if _user32.GetForegroundWindow() == hwnd:
                        break
                    time.sleep(0.05)

            # ① 영웅 클릭 → Ctrl+영웅번호, Ctrl+9
            hx, hy = _scale_coords(62, 88)
            click_image_center(hx, hy)
            time.sleep(0.2)
            _press_vk(_VK_CONTROL)
            _press_vk(hero_vk);       time.sleep(0.05)
            _press_vk(hero_vk, keyup=True); time.sleep(0.05)
            _press_vk(_VK_9);         time.sleep(0.05)
            _press_vk(_VK_9, keyup=True)
            _press_vk(_VK_CONTROL, keyup=True)
            time.sleep(0.2)
            self.log(f"영웅 부대지정: Ctrl+{hero_num} + Ctrl+9", "info")

            # ② 창고 클릭 → Ctrl+창고번호, Ctrl+0
            sx, sy = _scale_coords(57, 738)
            click_image_center(sx, sy)
            time.sleep(0.2)
            _press_vk(_VK_CONTROL)
            _press_vk(storage_vk);    time.sleep(0.05)
            _press_vk(storage_vk, keyup=True); time.sleep(0.05)
            _press_vk(_VK_0);         time.sleep(0.05)
            _press_vk(_VK_0, keyup=True)
            _press_vk(_VK_CONTROL, keyup=True)
            time.sleep(0.2)
            self.log(f"창고 부대지정: Ctrl+{storage_num} + Ctrl+0", "info")

            # ③ 검증 1: 영웅번호 키 → 최대 3초 내 22번 감지되면 통과
            _press_vk(hero_vk);       time.sleep(0.05)
            _press_vk(hero_vk, keyup=True)
            ok22_hero = False
            deadline22 = time.time() + 3
            while self._running and time.time() < deadline22:
                ok22_hero, _, _, _ = _image_match(IMG.UNIT_GROUP, background=True)
                if ok22_hero:
                    break
                time.sleep(0.25)
            if not ok22_hero:
                if self._running:
                    self.log(f"[검증 실패] 영웅({hero_num}번) 22번 미감지 → 재시도", "warn")
                continue
            self.log(f"[검증 통과] 영웅({hero_num}번) 확인", "success")

            # ④ 검증 2: 창고번호 키 → 최대 3초 내 22번 미감지면 통과
            _press_vk(storage_vk);    time.sleep(0.05)
            _press_vk(storage_vk, keyup=True)
            ok22_storage = False
            deadline22 = time.time() + 3
            while self._running and time.time() < deadline22:
                ok22_storage, _, _, _ = _image_match(IMG.UNIT_GROUP, background=True)
                if not ok22_storage:
                    break
                time.sleep(0.25)
            if ok22_storage:
                if self._running:
                    self.log(f"[검증 실패] 창고({storage_num}번) 22번 감지됨 → 재시도", "warn")
                continue
            self.log(f"[검증 통과] 창고({storage_num}번) 확인", "success")

            self.log("부대지정 완료!", "success")
            self.status("부대지정 완료!", GREEN)
            _press_vk(hero_vk); time.sleep(0.05)
            _press_vk(hero_vk, keyup=True)
            self.log(f"영웅 재선택: {hero_num}번 키 입력", "info")
            break

    def _run_ingame(self):
        """인게임 루틴. 백그라운드 워처가 이벤트 감지 시 재시작 or 종료."""
        while self._running:
            # ── 인게임 상태 확인 ──
            self.log("인게임 상태 확인 → 부대지정 검증 시작", "info")
            self.status("인게임 확인 중...", YELLOW)
            ok, _ = self._wait_for_image(IMG.INGAME_CHECK, timeout=10,
                                         click=False, background=True)
            if not ok:
                self.log("[오류] 인게임 상태 확인 실패 → 중단", "error")
                self.status("인게임 확인 실패", RED)
                return

            # ── 백그라운드 워처 시작 (옵션 체크) ──
            if not load_config().get("ingame_restart_on_event", True):
                # 옵션 꺼져 있으면 워처 없이 루틴만 실행 후 대기
                if load_config().get("auto_hunt", False):
                    self._run_auto_hunt()
                if not self._running: return
                if load_config().get("control_group_enabled", True):
                    self._assign_control_groups()
                else:
                    self.log("부대지정 스킵", "info")
                if not self._running: return
                if self._portal_active():
                    self._enter_portal_suicide()
                if not self._running: return
                self.log("인게임 매크로 완료 → 대기 중...", "success")
                self.status("인게임 대기 중...", GREEN)
                while self._running:
                    self._sleep(1)
                return

            event_flag   = threading.Event()   # 이벤트 감지 시 SET
            event_reason = [None]              # 감지 이유 저장 (리스트로 mutable)

            def _watcher():
                while self._running and not event_flag.is_set():
                    m42, _, coords42, size42 = _image_match(IMG.PLAYER_LEFT, background=True)
                    m41, _, coords41, size41 = _image_match(IMG.MISSION_END, background=True)
                    first_match = m42 or m41
                    if first_match:
                        reason_candidate = "player_left" if m42 else "mission_end"
                        coords_c = coords42 if m42 else coords41
                        size_c   = size42   if m42 else size41
                        self.log(f"이벤트 후보 감지 ({reason_candidate}) → 0.25초 간격 5회 확인 시작", "warn")
                        confirm = 0
                        for _ in range(5):
                            time.sleep(0.25)
                            if not self._running or event_flag.is_set():
                                return
                            cm42, _, _, _ = _image_match(IMG.PLAYER_LEFT, background=True)
                            cm41, _, _, _ = _image_match(IMG.MISSION_END, background=True)
                            if cm42 or cm41:
                                confirm += 1
                        if confirm == 5:
                            if coords_c:
                                self.overlay_signal.emit(coords_c[0], coords_c[1], size_c[0], size_c[1])
                            self.log(f"이벤트 확정 ({reason_candidate}) → -save 전송 후 War3 종료", "warn")
                            self._send_chat_instant("-save")
                            time.sleep(1)
                            for p in psutil.process_iter(['name']):
                                if p.info['name'].lower() == 'war3.exe':
                                    try:
                                        p.kill()
                                        self.log("War3.exe 강제 종료 (이벤트 감지)", "info")
                                    except Exception as e:
                                        self.log(f"[경고] War3 종료 실패: {e}", "warn")
                            event_reason[0] = reason_candidate
                            event_flag.set()
                            break
                        else:
                            self.log(f"오감지 ({confirm}/5) → 계속 감시", "info")
                    time.sleep(1)

            # ── 자동 세이브 워처 ──
            def _auto_save_watcher():
                cfg = load_config()
                if not cfg.get("auto_save_enabled", True):
                    return
                interval = max(300, cfg.get("auto_save_interval", 300))
                self.log(f"자동 세이브 워처 시작 ({interval}초 간격)", "info")
                elapsed = 0
                while self._running and not event_flag.is_set():
                    time.sleep(1)
                    elapsed += 1
                    if elapsed >= interval:
                        self.log("자동 세이브 실행 (-save)", "info")
                        self._send_chat_instant("-save")
                        elapsed = 0

            watcher         = threading.Thread(target=_watcher,          daemon=True)
            auto_save_watch = threading.Thread(target=_auto_save_watcher, daemon=True)
            watcher.start()
            auto_save_watch.start()

            # ── 메인 루틴 실행 (워처와 병렬) ──
            if load_config().get("auto_hunt", False):
                self._run_auto_hunt()
            if not self._running:
                event_flag.set()
                return
            if load_config().get("control_group_enabled", True):
                self._assign_control_groups()
            else:
                self.log("부대지정 스킵", "info")
            if not self._running:
                event_flag.set()
                return
            if self._portal_active():
                self._enter_portal_suicide()
            if not self._running:
                event_flag.set()
                return

            self.log("인게임 매크로 완료 → 이벤트 대기 중...", "success")
            self.status("인게임 대기 중...", GREEN)

            # ── 워처가 이벤트를 감지할 때까지 대기 ──
            while self._running and not event_flag.is_set():
                self._sleep(1)

            event_flag.set()   # 워처 종료 보장
            watcher.join(timeout=3)

            if not self._running:
                return

            # ── 이벤트 감지 후 인게임 여부 판단 ──
            reason = event_reason[0]
            self.log(f"이벤트 감지: {reason}", "warning")
            if image_exists(IMG.INGAME_CHECK, background=True):
                self.log("인게임 유지 → 루틴 재시작", "info")
                self.status("루틴 재시작...", YELLOW)
                continue
            else:
                self.log("인게임 종료 → 재시작 준비", "warning")
                self.status("인게임 종료 감지", RED)
                return

    # ── 폴링 헬퍼 ─────────────────────────────────
    def _wait_for_process(self, name: str, timeout: float) -> "psutil.Process | None":
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._running:
                return None
            for p in psutil.process_iter(['name']):
                if p.info['name'].lower() == name.lower():
                    return p
            if not self._sleep(1):
                return None
        return None

    def _wait_for_hwnd(self, timeout: float) -> "int | None":
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._running:
                return None
            hwnd = find_war3_hwnd()
            if hwnd:
                return hwnd
            if not self._sleep(1):
                return None
        return None

    def _wait_for_image(self, filename: str, timeout: float,
                        threshold: float = 0.8, interval: float = 0.25,
                        click: bool = True,
                        background: bool = False,
                        silent: bool = False,
                        edges: bool = False) -> "tuple[bool, tuple|None]":
        """이미지 서치. click=True 이면 감지 즉시 중앙 클릭.
        background=True 이면 PrintWindow 비활성 서치.
        silent=True 이면 로그 출력 없음.
        edges=True 이면 Canny 엣지 매칭 → 배경 변화에 강인.
        반환: (성공여부, 클릭좌표|None)"""
        prefix = "[비활성서치]" if background else "[서치]"
        first = True
        start_t  = time.time()
        deadline = start_t + timeout
        while time.time() < deadline:
            if not self._running:
                return False, None
            try:
                matched, val, coords, tmpl_size = _image_match(filename, threshold,
                                                               background=background,
                                                               edges=edges)
            except Exception as e:
                self.log_signal.emit(f"[{now()}] [오류] _image_match 예외: {e}", "error")
                if not self._sleep(interval): return False, None
                continue
            remaining = max(0.0, deadline - time.time())  # 매치 완료 후 실제 남은 시간
            if val < 0:
                msg   = f"{prefix} {filename} → WC3 창 없음  ({remaining:.1f}s 남음)"
                level = "warn"
            else:
                bar = "█" * int(val * 10) + "░" * (10 - int(val * 10))
                if matched:
                    msg, level = f"{prefix} {filename} → 감지! [{bar}] {val:.3f}", "success"
                    if not silent:
                        self.log_signal.emit(f"[{now()}] {msg}", level)
                    if coords and tmpl_size[0] > 0:
                        self.overlay_signal.emit(coords[0], coords[1],
                                                 tmpl_size[0], tmpl_size[1])
                    if click and coords:
                        self.log_signal.emit(
                            f"[{now()}] 클릭: ({coords[0]}, {coords[1]})", "info")
                        click_image_center(coords[0], coords[1])
                    return True, coords
                else:
                    msg   = f"{prefix} {filename} → 미감지  [{bar}] {val:.3f}  ({remaining:.1f}s 남음)"
                    level = "warn"
            # 첫 번째 미감지/WC3없음만 1회 출력, 이후 반복은 무시 (update_signal 제거 → 다른 스레드 로그 덮어쓰기 방지)
            if not silent and first:
                self.log_signal.emit(f"[{now()}] {msg}", level)
                first = False
            if not self._sleep(interval): return False, None
        elapsed = time.time() - start_t
        if not silent:
            self.log_signal.emit(
                f"[{now()}] [타임아웃] {filename} — {elapsed:.1f}초 경과", "warn")
        return False, None

    def _login_loop(self) -> bool:
        """1번 클릭 후 2번 1초 대기 루프 → 3번 20초 대기.
        3번 감지 성공 시 True, 워커 중단 시 False."""
        while self._running:
            # ── 2번 감지 루프: 1초 내 미감지 → 1번 재서치+클릭 ──
            self.log("2.로그인화면입장감지.png 대기 중...", "info")
            self.status("로그인 진입 감지 중...", YELLOW)
            coords2 = None
            while self._running:
                ok2, coords2 = self._wait_for_image(
                    IMG.LOGIN_ENTER, timeout=1, click=False)
                if ok2:
                    break
                # 1초 내 2번 미감지 → 1번 재서치+클릭
                self.log("2번 미감지 (1s) → 1번 재서치+클릭", "warn")
                self.status("메인화면 재클릭 중...", YELLOW)
                self._wait_for_image(IMG.MAIN_SCREEN, timeout=30, click=True)

            if not self._running:
                return False

            # ── 3번: 실제 로그인 화면 20초 대기 (클릭 없음) ──
            self.log("3.로그인화면.png 감지 대기 중... (최대 20초)", "info")
            self.status("로그인 화면 대기 중...", YELLOW)
            ok3, _ = self._wait_for_image(IMG.LOGIN_SCREEN, timeout=20, click=False)
            if ok3:
                self.log("로그인 화면 진입 완료!", "success")
                pw = decrypt_password(load_config().get("bnet_password", ""))
                if not pw:
                    self.log("[경고] 비밀번호가 설정되지 않았습니다.", "warn")
                else:
                    while self._running:
                        self.status("비밀번호 입력 중...", YELLOW)
                        if not self._sleep(0.5): return False  # 화면 안정화
                        hwnd = find_war3_hwnd()
                        if hwnd:
                            _user32.SetForegroundWindow(hwnd)
                            if not self._sleep(0.1): return False
                        self.log(f"비밀번호 입력 중... ({len(pw)}자)", "info")
                        type_string(pw)
                        if not self._sleep(0.1): return False
                        press_enter()
                        self.log("비밀번호 입력 + 엔터 완료", "success")

                        # ── 6번: 비밀번호 틀렸을 때 이미지 체크 ──
                        ok6, coords6 = self._wait_for_image(
                            IMG.LOGIN_WRONG_PW, timeout=3, click=False)
                        if ok6 and coords6:
                            self.log("비밀번호 오류 감지 → 클릭 후 재입력", "warn")
                            self.status("비밀번호 오류 재시도 중...", RED)
                            click_image_center(coords6[0], coords6[1])
                            if not self._sleep(1): return
                            continue  # 비밀번호 재입력
                        break  # 6번 미감지 → 정상 통과

                # ── 4번: 이미지 감지 후 C 키 입력 ──
                self.log("4번 이미지 대기 중...", "info")
                self.status("4번 이미지 감지 중...", YELLOW)
                ok4, _ = self._wait_for_image(IMG.LOBBY, timeout=30, click=False)
                if ok4:
                    # C 입력 후 5번 미감지 시 재시도 루프
                    while self._running:
                        hwnd = find_war3_hwnd()
                        if hwnd:
                            _user32.SetForegroundWindow(hwnd)
                            if not self._sleep(0.1): return False
                        self.log("4번 감지 → C 키 입력", "info")
                        _press_vk(_VK_C); time.sleep(0.05)
                        _press_vk(_VK_C, keyup=True)

                        self.log("5.커스텀채널입장.png 대기 중... (5초)", "info")
                        self.status("커스텀채널 감지 중...", YELLOW)
                        ok5, _ = self._wait_for_image(IMG.CUSTOM_CHANNEL, timeout=5, click=False)
                        if ok5:
                            break
                        self.log("5번 미감지 (5s) → 포커스+C 재입력", "warn")
                else:
                    self.log("[경고] 4번 이미지 감지 실패 (30초)", "warn")
                    ok5 = False

                # ── 5번: 커스텀채널입장 감지됨 ──
                if ok5:
                    if not self._running: return False
                    role = load_config().get("role", "freematch")

                    # 프리매치: 커스텀채널 입장 완료 → 프리매치 루프 실행
                    if role == "freematch":
                        self.log("프리매치: 커스텀채널 입장 완료", "success")
                        self._freematch_loop()
                        return True

                    proceed = True
                    if role != "freematch":
                        # 방장/승객: 방 제목 입력 + 선택 + 복사
                        room_name = load_config().get("room_name", "")
                        if room_name:
                            hwnd = find_war3_hwnd()
                            if hwnd:
                                _user32.SetForegroundWindow(hwnd)
                                if not self._sleep(0.1): return False
                            self.log(f"방 제목 입력: {room_name}", "info")
                            type_string(room_name)
                            if not self._sleep(0.1): return False
                            n = len(room_name)
                            _press_vk(_VK_SHIFT)
                            for _ in range(n):
                                _press_vk(_VK_LEFT, extended=True); time.sleep(0.02)
                                _press_vk(_VK_LEFT, keyup=True, extended=True); time.sleep(0.02)
                            _press_vk(_VK_SHIFT, keyup=True)
                            if not self._sleep(0.2): return False
                            _press_vk(_VK_CONTROL)
                            _press_vk(_VK_C); time.sleep(0.02)
                            _press_vk(_VK_C, keyup=True)
                            _press_vk(_VK_CONTROL, keyup=True)
                            if not self._sleep(0.2): return False
                            self.log("방 제목 입력 + 선택 + 복사 완료", "success")
                        else:
                            self.log("[경고] 방 제목이 설정되지 않았습니다.", "warn")
                            proceed = False

                    if proceed:
                        # ── Tab + G ──
                        _press_vk(_VK_TAB); time.sleep(0.02)
                        _press_vk(_VK_TAB, keyup=True); time.sleep(0.3)
                        _press_vk(_VK_G); time.sleep(0.02)
                        _press_vk(_VK_G, keyup=True); time.sleep(0.3)
                        self.log("Tab + G 입력 완료", "info")

                        # ── 7번: 방 목록 입장 서치 ──
                        self.log("7.방목록입장.png 대기 중...", "info")
                        self.status("방 목록 감지 중...", YELLOW)
                        self._wait_for_image(IMG.ROOM_LIST, timeout=15, click=False)
                        if not self._running: return False

                        # ── 역할 분기 ──
                        if role == "guest":
                            self._guest_loop()
                        else:
                            self._host_loop()
                        if not self._running: return False
                else:
                    self.log("[경고] 5번 이미지 감지 실패 (30초)", "warn")
                self.status("완료!", GREEN)
                return True

            # ── 20초 타임아웃 → 복구 루틴 ──
            if not self._running:
                return False
            self.log("[경고] 20초 내 로그인 화면 미진입 → 복구 루틴 실행", "warn")
            self.status("복구 중...", RED)

            # 2번이 처음 감지됐던 좌표로 바로 클릭 (재서치 없이)
            if coords2:
                self.log(f"2번 저장 좌표로 클릭: ({coords2[0]}, {coords2[1]})", "info")
                click_image_center(coords2[0], coords2[1])
            else:
                self.log("2번 저장 좌표 없음 → 재서치...", "warn")
                self._wait_for_image(IMG.LOGIN_ENTER, timeout=30, click=True)

            if not self._sleep(1): return

            # 1번 재서치+클릭 → 루프 처음(2번 서치)으로 돌아감
            self.log("1.메인화면.png 재서치 + 클릭...", "info")
            self.status("메인화면 재진입 중...", YELLOW)
            self._wait_for_image(IMG.MAIN_SCREEN, timeout=30, click=True)

        return False

    def _guest_loop(self):
        """승객 전용: Ctrl+V+Enter → 방 입장 or 실패 복구 무한 루프.
        8.방입장체크(동맹).png 감지 시 종료."""
        self.log("=== 승객 매크로 시작 ===", "info")
        while self._running:
            # Ctrl+V → Enter
            self.status("방 제목 붙여넣기 중...", YELLOW)
            hwnd = find_war3_hwnd()
            if hwnd:
                _user32.SetForegroundWindow(hwnd)
                if not self._sleep(0.1): return
            _press_vk(_VK_CONTROL)
            _press_vk(_VK_V); time.sleep(0.02)
            _press_vk(_VK_V, keyup=True)
            _press_vk(_VK_CONTROL, keyup=True)
            time.sleep(0.3)
            _press_vk(_VK_RETURN); time.sleep(0.02)
            _press_vk(_VK_RETURN, keyup=True)
            self.log("Ctrl+V + Enter 입력 완료", "info")

            # ── 6번(실패) or 8번(성공) 감지 ──
            self.log("6번(입장 실패) / 8번(입장 성공) 감지 대기 중...", "info")
            self.status("방 입장 대기 중...", YELLOW)
            deadline = time.time() + 30
            joined = False
            first8g = True
            while self._running and time.time() < deadline:
                ok6, _, coords6, _ = _image_match(IMG.LOGIN_WRONG_PW)
                if ok6 and coords6:
                    self.log("입장 실패 감지 → 클릭 → ESC → 5번 재서치", "warn")
                    self.status("입장 실패 복구 중...", RED)
                    click_image_center(coords6[0], coords6[1])
                    if not self._sleep(1): return
                    # ESC → 5번 감지 루프
                    while self._running:
                        _press_vk(_VK_ESCAPE); time.sleep(0.02)
                        _press_vk(_VK_ESCAPE, keyup=True)
                        ok5, _ = self._wait_for_image(
                            IMG.CUSTOM_CHANNEL, timeout=5, click=False)
                        if ok5:
                            break
                        self.log("5번 미감지 → ESC 재시도", "warn")
                    # Tab + G → 7번 → 다음 Ctrl+V 시도
                    _press_vk(_VK_TAB); time.sleep(0.02)
                    _press_vk(_VK_TAB, keyup=True); time.sleep(0.3)
                    _press_vk(_VK_G); time.sleep(0.02)
                    _press_vk(_VK_G, keyup=True); time.sleep(0.3)
                    self.log("Tab + G 재입력", "info")
                    self._wait_for_image(IMG.ROOM_LIST, timeout=15, click=False)
                    if not self._running: return
                    first8g = True
                    break  # 다시 Ctrl+V 루프로

                ok8, val8g, _, _ = _image_match(IMG.ROOM_ENTER)
                remaining8g = max(0.0, deadline - time.time())
                if val8g >= 0:
                    bar8g = "█" * int(val8g * 10) + "░" * (10 - int(val8g * 10))
                    if ok8:
                        msg8g = f"[서치] 8.방입장체크(동맹).png → 감지! [{bar8g}] {val8g:.3f}"
                        self.log_signal.emit(f"[{now()}] {msg8g}", "success")
                        self.status("방 입장 완료!", GREEN)
                        joined = True
                        break
                    else:
                        msg8g = f"[서치] 8.방입장체크(동맹).png → 미감지  [{bar8g}] {val8g:.3f}  ({remaining8g:.1f}s 남음)"
                else:
                    msg8g = f"[서치] 8.방입장체크(동맹).png → WC3 창 없음  ({remaining8g:.1f}s 남음)"
                if first8g:
                    self.log_signal.emit(f"[{now()}] {msg8g}", "warn")
                    first8g = False

                if not self._sleep(0.25): return

            if joined:
                result = self._wait_loading()
                if result == "loaded":
                    return
                if result == "ejected":
                    # 5번 → Tab+G → 7번 → Ctrl+V 루프 재시작
                    self.log("로딩 중 강퇴/이탈 → 방 목록 재진입", "warn")
                    _press_vk(_VK_TAB); time.sleep(0.02)
                    _press_vk(_VK_TAB, keyup=True); time.sleep(0.3)
                    _press_vk(_VK_G); time.sleep(0.02)
                    _press_vk(_VK_G, keyup=True); time.sleep(0.3)
                    self._wait_for_image(IMG.ROOM_LIST, timeout=15, click=False)
                    if not self._running: return
                    continue  # Ctrl+V 루프 처음으로
                return  # "timeout": War3 재실행됨 → 워커 종료
            if not self._running:
                return

    def _freematch_loop(self):
        """프리매치: hera.pet API → 필터 → 랜덤 선택 → 방제입력+복사+Tab+G → 방 입장 무한 루프."""
        from src.utils.room_list import fetch_rooms

        self.log("=== 프리매치 매크로 시작 ===", "info")

        while self._running:
            cfg = load_config()
            fm_room        = cfg.get("fm_room_name", "").strip()
            fm_host_filter = cfg.get("fm_host", "").strip()
            fm_map         = cfg.get("fm_map_name", "NOX RPG").strip()
            fm_max         = cfg.get("fm_max_players", 6)
            map_keyword    = fm_map if fm_map else "NOX"

            # ── 방 목록 조회 ──
            self.status("방 목록 조회 중...", YELLOW)
            rooms = fetch_rooms(map_keyword)
            if not rooms:
                self.log(f"방 목록 없음 (keyword={map_keyword}) → 재시도", "warn")
                if not self._sleep(1): return
                continue

            # ── 필터링 (방제/방장/인원/블랙리스트) ──
            candidates = []
            for room in rooms:
                if time.time() < self._fm_blacklist.get(room["id"], 0):
                    continue
                if room["players"] >= fm_max:
                    continue
                if fm_room and fm_room.lower() not in room["name"].lower():
                    continue
                if fm_host_filter and fm_host_filter.lower() not in room["host"].lower():
                    continue
                candidates.append(room)

            if not candidates:
                self.log("조건에 맞는 방 없음 → 재시도", "warn")
                if not self._sleep(1): return
                continue

            # ── 랜덤 선택 ──
            room = random.choice(candidates)
            self.log(
                f"방 선택: [{room['id']}] {room['name']} / 방장: {room['host']} / 인원: {room['players']}",
                "info"
            )

            # ── 커스텀채널 검색창에 방 제목 입력 → 선택 → 복사 ──
            hwnd = find_war3_hwnd()
            if hwnd:
                _user32.SetForegroundWindow(hwnd)
                if not self._sleep(0.1): return
            self.log(f"방 제목 입력: {room['name']}", "info")
            type_string(room["name"])
            if not self._sleep(0.1): return
            n = len(room["name"])
            _press_vk(_VK_SHIFT)
            for _ in range(n):
                _press_vk(_VK_LEFT, extended=True); time.sleep(0.02)
                _press_vk(_VK_LEFT, keyup=True, extended=True); time.sleep(0.02)
            _press_vk(_VK_SHIFT, keyup=True)
            if not self._sleep(0.1): return
            _press_vk(_VK_CONTROL)
            _press_vk(_VK_C); time.sleep(0.02)
            _press_vk(_VK_C, keyup=True)
            _press_vk(_VK_CONTROL, keyup=True)
            if not self._sleep(0.1): return
            self.log("방 제목 입력 + 선택 + 복사 완료", "info")

            # ── Tab + G → 7번(방목록) 대기 ──
            _press_vk(_VK_TAB); time.sleep(0.02)
            _press_vk(_VK_TAB, keyup=True); time.sleep(0.3)
            _press_vk(_VK_G); time.sleep(0.02)
            _press_vk(_VK_G, keyup=True)
            self.log("Tab + G 입력", "info")

            ok7, _ = self._wait_for_image(IMG.ROOM_LIST, timeout=15, click=False)
            if not self._running: return
            if not ok7:
                self.log("7번(방목록) 미감지 → 재시도", "warn")
                continue

            # ── Ctrl+V → Enter (방 이름 붙여넣기 후 입장) ──
            if not self._sleep(0.2): return
            _press_vk(_VK_CONTROL)
            _press_vk(_VK_V); time.sleep(0.02)
            _press_vk(_VK_V, keyup=True)
            _press_vk(_VK_CONTROL, keyup=True)
            time.sleep(0.1)
            _press_vk(_VK_RETURN); time.sleep(0.02)
            _press_vk(_VK_RETURN, keyup=True)
            self.log("Ctrl+V + Enter 입력", "info")

            # ── 8번(성공) or 6번(실패) 대기 (30초) ──
            deadline  = time.time() + 30
            joined    = False
            fail_by_6 = False
            first_log = True
            while self._running and time.time() < deadline:
                ok6, _, coords6, _ = _image_match(IMG.LOGIN_WRONG_PW)
                if ok6 and coords6:
                    self.log("입장 실패(6번) → 60초 블랙리스트 추가", "warn")
                    self._fm_blacklist[room["id"]] = time.time() + 60
                    click_image_center(coords6[0], coords6[1])
                    fail_by_6 = True
                    break

                ok8, val8, _, _ = _image_match(IMG.ROOM_ENTER)
                if ok8:
                    self.log("입장 성공(8번) 감지!", "success")
                    self.status("방 입장 완료!", GREEN)
                    joined = True
                    break

                remaining = max(0.0, deadline - time.time())
                msg = f"[서치] 8.방입장체크 → 대기 중... ({remaining:.1f}s 남음)"
                if first_log:
                    self.log_signal.emit(f"[{now()}] {msg}", "warn")
                    first_log = False
                if not self._sleep(0.25): return

            if not self._running: return

            if fail_by_6:
                # 1초 대기 후 ESC → 5번 재서치 → API 재조회
                if not self._sleep(1): return
                while self._running:
                    _press_vk(_VK_ESCAPE); time.sleep(0.02)
                    _press_vk(_VK_ESCAPE, keyup=True)
                    ok5, _ = self._wait_for_image(IMG.CUSTOM_CHANNEL, timeout=5, click=False)
                    if ok5:
                        break
                    self.log("5번 미감지 → ESC 재시도", "warn")
                continue

            if not joined:
                # 30초 내 미입장 → 블랙리스트 + 재시도
                self.log(f"30초 내 미입장 → 60초 블랙리스트: {room['id']}", "warn")
                self._fm_blacklist[room["id"]] = time.time() + 60
                continue

            # ── 방 입장 성공 → 로딩 대기 ──
            result = self._wait_loading(relaunch_on_timeout=False)
            if result == "loaded":
                return
            if result == "ejected":
                self.log("로딩 중 강퇴/이탈 → 60초 블랙리스트 추가 후 재시도", "warn")
                self._fm_blacklist[room["id"]] = time.time() + 60
                continue
            # timeout
            self.log("로딩 타임아웃(5분) → 60초 블랙리스트 추가 + War3 재실행", "error")
            self._fm_blacklist[room["id"]] = time.time() + 60
            self._relaunch_war3()
            return

    # ── War3 재실행 ──────────────────────────────────
    def _relaunch_war3(self):
        """War3.exe 강제 종료 후 JNLoader 재실행."""
        import subprocess
        for p in psutil.process_iter(['name']):
            if p.info['name'].lower() == 'war3.exe':
                try:
                    p.kill()
                    self.log("War3.exe 강제 종료", "info")
                except Exception as e:
                    self.log(f"[경고] War3 종료 실패: {e}", "warn")
        if not self._sleep(2): return
        cfg = load_config()
        jn_dir = cfg.get("jnloader_path", "")
        jn_exe = os.path.join(jn_dir, "JNLoader.exe")
        if not os.path.isfile(jn_exe):
            self.log(f"[경고] JNLoader.exe 없음: {jn_exe}", "warn")
            return
        mon_w = ctypes.windll.user32.GetSystemMetrics(0)
        mon_h = ctypes.windll.user32.GetSystemMetrics(1)
        is_fhd = (mon_w == 1920 and mon_h == 1080)
        ok, msg = patch_war3_preferences(is_fhd)
        self.log(msg, "info" if ok else "warn")
        use_window_arg = (not is_fhd) and (cfg.get("wc3_window_mode", "fullscreen") == "windowed")
        jn_cmd = [jn_exe, "-window"] if use_window_arg else [jn_exe]

        try:
            subprocess.Popen(jn_cmd, cwd=jn_dir)
            self.log("JNLoader.exe 재실행 완료 → 처음부터 재시작", "success")
        except Exception as e:
            self.log(f"[오류] JNLoader 재실행 실패: {e}", "error")

    # ── 캐릭터 선택 루프 ──────────────────────────────
    def _select_character(self):
        """캐릭터 이미지 서치 → 더블클릭 → 21.캐릭터선택체크.png 검증 루프.
        21번 감지 시 종료."""
        char_name = load_config().get("character", next(iter(_CHAR_IMAGES)))
        img_file  = _CHAR_IMAGES.get(char_name)
        if not img_file:
            self.log(f"[경고] 캐릭터 이미지 매핑 없음: {char_name}", "warn")
            return

        self.log(f"캐릭터 선택 시작: {char_name} ({img_file})", "info")
        self.status(f"캐릭터 선택 중... ({char_name})", YELLOW)

        while self._running:
            # ① 캐릭터 이미지 서치 (최대 10초)
            ok_c, coords_c = self._wait_for_image(img_file, timeout=10, click=False)
            if not ok_c or not coords_c:
                self.log(f"{char_name} 이미지 미감지 → 재시도", "warn")
                continue

            # ② 커서 이동 + 더블클릭
            self.log(f"{char_name} 감지 → 더블클릭", "info")
            click_image_center(coords_c[0], coords_c[1])
            time.sleep(0.15)
            click_image_center(coords_c[0], coords_c[1])

            # ③ 21.캐릭터선택체크.png 검증 (5초)
            ok21, _ = self._wait_for_image(IMG.CHAR_SELECT, timeout=5, click=False)
            if ok21:
                self.log("캐릭터 선택 완료! (21번 이미지 감지)", "success")
                self.status("캐릭터 선택 완료!", GREEN)
                break
            self.log("21번 미감지 (5s) → 캐릭터 재선택", "warn")

    # ── 로딩 완료 대기 ────────────────────────────────
    def _wait_loading(self, relaunch_on_timeout: bool = True) -> str:
        """8번 감지 후 11.로딩완료.png 를 300초 대기.
        0.25초마다 5.커스텀채널입장.png 도 체크 (강퇴/이탈 감지).
        relaunch_on_timeout=False 면 타임아웃 시 War3 재실행 없이 반환.
        반환: 'loaded' | 'ejected' | 'timeout'"""
        self.log("11.로딩완료.png 대기 중... (최대 300초)", "info")
        self.status("게임 로딩 대기 중...", YELLOW)
        deadline = time.time() + 300
        first = True
        while self._running and time.time() < deadline:
            # 강퇴/이탈 체크 (5번)
            try:
                ok5, val5, _, _ = _image_match(IMG.CUSTOM_CHANNEL)
            except Exception as e:
                self.log_signal.emit(f"[{now()}] [오류] 5번 서치 예외: {e}", "error")
                time.sleep(0.25)
                continue
            if ok5:
                self.log("5번 감지 → 방 이탈/강퇴!", "warn")
                self.status("방 이탈 감지!", RED)
                return "ejected"
            # 로딩 완료 체크 (11번)
            try:
                ok11, val11, _, _ = _image_match(IMG.LOADING_DONE)
            except Exception as e:
                self.log_signal.emit(f"[{now()}] [오류] 11번 서치 예외: {e}", "error")
                time.sleep(0.25)
                continue
            if ok11:
                self.log("데이터 셋 로드 완료!!", "error")  # error = 빨간색
                self.status("게임 로딩 완료!", GREEN)
                ok13, _, coords13, _ = _image_match(IMG.LOADING_CURSOR)
                if ok13 and coords13:
                    move_cursor_to(coords13[0], coords13[1])
                    self.log("커서 이동 완료 (13.로딩완료후커서이동.png)", "info")
                    self._select_character()
                    if not self._running: return "loaded"
                    # 5초 안정성 대기
                    for sec in range(5, 0, -1):
                        if not self._running:
                            return "loaded"
                        self.log(f"안정화 대기: {sec}초...", "info")
                        self.status(f"안정화 중... ({sec}s)", YELLOW)
                        if not self._sleep(1.0): return "stopped"
                    # 출석체크
                    if load_config().get("attendance_check", True):
                        self.log("출석체크 서치 시작 (23.출석체크.png, 최대 5초)", "info")
                        self.status("출석체크 중...", YELLOW)
                        self._wait_for_image(IMG.ATTENDANCE, timeout=5, click=True)
                return "loaded"
            remaining = max(0.0, deadline - time.time())
            val11_clamped = max(0.0, min(1.0, val11))
            bar = "█" * int(val11_clamped * 10) + "░" * (10 - int(val11_clamped * 10))
            conf_str = f"{val11:.3f}" if val11 >= 0 else "WC3없음"
            msg = f"[{now()}] [서치] 11.로딩완료.png → 미감지  [{bar}] {conf_str}  ({remaining:.0f}s 남음)"
            if first:
                self.log_signal.emit(msg, "warn")
                first = False
            time.sleep(0.25)

        if not self._running:
            return "timeout"
        # 300초 타임아웃
        if relaunch_on_timeout:
            self.log("[치명] 300초 내 로딩 미완료 → War3 재실행 후 처음부터", "error")
            self.status("War3 재실행 중...", RED)
            self._relaunch_war3()
        else:
            self.log("300초 내 로딩 미완료 → 타임아웃", "error")
        return "timeout"

    # ── 인게임 채팅 입력 ─────────────────────────────
    def _send_ingame_chat(self, text: str):
        """Enter → 텍스트 입력 → Enter 로 인게임 채팅 전송."""
        hwnd = find_war3_hwnd()
        if hwnd:
            _user32.SetForegroundWindow(hwnd)
            time.sleep(0.1)
        self.log(f"채팅 입력: {text}", "info")
        _press_vk(_VK_RETURN); time.sleep(0.1)
        _press_vk(_VK_RETURN, keyup=True); time.sleep(0.2)
        type_string(text)
        time.sleep(0.1)
        _press_vk(_VK_RETURN); time.sleep(0.02)
        _press_vk(_VK_RETURN, keyup=True)
        self.log(f"채팅 전송 완료: {text}", "success")

    def _send_chat_fast(self, text: str):
        """클립보드 붙여넣기 방식으로 빠르게 채팅 커맨드 전송 (Enter → Ctrl+V → Enter)."""
        import win32clipboard
        hwnd = find_war3_hwnd()
        if not hwnd:
            self.log("[채팅] WC3 창 없음", "warn")
            return
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        _user32.SetForegroundWindow(hwnd)
        time.sleep(0.05)
        _press_vk(_VK_RETURN);          time.sleep(0.02)
        _press_vk(_VK_RETURN, keyup=True); time.sleep(0.05)
        _press_vk(_VK_CONTROL)
        _press_vk(_VK_V);               time.sleep(0.02)
        _press_vk(_VK_V, keyup=True)
        _press_vk(_VK_CONTROL, keyup=True); time.sleep(0.05)
        _press_vk(_VK_RETURN);          time.sleep(0.02)
        _press_vk(_VK_RETURN, keyup=True)
        self.log(f"[채팅] 전송: {text}", "success")

    def _send_chat_instant(self, text: str):
        """단일 SendInput 배치로 딜레이 없이 채팅 전송. KEYEVENTF_UNICODE로 한글 포함 전 유니코드 지원."""
        hwnd = find_war3_hwnd()
        if not hwnd:
            self.log("[채팅] WC3 창 없음", "warn")
            return
        _user32.SetForegroundWindow(hwnd)
        deadline_fg = time.time() + 1.0
        while time.time() < deadline_fg:
            if _user32.GetForegroundWindow() == hwnd:
                break
            time.sleep(0.05)
        # 이벤트 목록: Enter↓↑ + 문자별 Unicode↓↑ + Enter↓↑ — 단일 배치
        events: list[tuple[int, int, int]] = []  # (vk, scan, flags)
        events.append((_VK_RETURN, _user32.MapVirtualKeyW(_VK_RETURN, 0), 0))
        events.append((_VK_RETURN, _user32.MapVirtualKeyW(_VK_RETURN, 0), _KEYEVENTF_KEYUP))
        for ch in text:
            code = ord(ch)
            events.append((0, code, _KEYEVENTF_UNICODE))
            events.append((0, code, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP))
        events.append((_VK_RETURN, _user32.MapVirtualKeyW(_VK_RETURN, 0), 0))
        events.append((_VK_RETURN, _user32.MapVirtualKeyW(_VK_RETURN, 0), _KEYEVENTF_KEYUP))
        arr = (_KBD_INPUT * len(events))()
        for i, (vk, scan, flags) in enumerate(events):
            ctypes.memset(ctypes.byref(arr[i]), 0, ctypes.sizeof(_KBD_INPUT))
            arr[i].type       = 1  # INPUT_KEYBOARD
            arr[i].ki.wVk     = vk
            arr[i].ki.wScan   = scan
            arr[i].ki.dwFlags = flags
        _user32.SendInput(len(events), arr, ctypes.sizeof(_KBD_INPUT))
        self.log(f"[채팅] 즉시 전송: {text}", "success")

    def _enter_portal_suicide(self):
        """-suicide 전송 후 31.정지.png 감지될 때까지 무한 재시도."""
        attempt = 0
        while self._running:
            attempt += 1
            self.log(f"[포탈] -suicide 전송 (시도 {attempt}회)", "info")
            self.status("포탈 진입 중...", YELLOW)
            self._send_chat_instant("-suicide")
            time.sleep(1.0)
            # 34.공격(x).png 서치 — 미감지 시 영웅 미선택 상태로 판단, 영웅 선택 후 재시도
            ok_atk, _ = self._wait_for_image(IMG.ATTACK_X, timeout=5.0, threshold=0.90, click=False)
            if not ok_atk:
                self.log("[포탈] 공격X 미감지 → 영웅 선택 후 재시도", "warn")
                move_cursor_to(55, 80)
                time.sleep(0.05)
                click_image_center(55, 80)
                continue
            ok, _ = self._wait_for_image(IMG.STOP, timeout=5.0, click=False)
            if ok:
                self.log("[포탈] 정지 화면 확인 → 자살 성공", "success")
                self.status("포탈 이동 중...", YELLOW)
                # (34, 849) 좌더블클릭
                move_cursor_to(34, 849)
                time.sleep(0.05)
                click_image_center(34, 849)
                time.sleep(0.1)
                click_image_center(34, 849)
                # 1초 병렬 타이머 동안 0.25초마다 우클릭
                deadline = time.time() + 1.0
                while self._running and time.time() < deadline:
                    right_click_image_center(34, 849)
                    time.sleep(0.25)
                # 30.이동(X).png 서치 (5초) — 미감지 시 suicide 루프 처음으로
                ok_move, _ = self._wait_for_image(IMG.MOVE_X, timeout=5.0, click=False)
                if ok_move:
                    self.log("[포탈] 이동 확인 → 포탈 진입 중...", "success")
                    self.status("포탈 진입 중...", YELLOW)
                    move_cursor_to(1042, 344)
                    time.sleep(0.05)
                    click_image_center(1042, 344)
                    time.sleep(0.1)
                    click_image_center(1042, 344)
                    # 35.포탈검증.png 서치 (5초) — 미감지 시 suicide 루프 처음으로
                    ok_portal, _ = self._wait_for_image(IMG.PORTAL_CHECK, timeout=5.0, click=False)
                    if ok_portal:
                        self.log("[포탈] 포탈 검증 완료", "success")
                        self.status("포탈 검증 완료", GREEN)
                        # 설정된 포탈 키 좌표로 이동 후 좌클릭
                        _cfg = load_config()
                        if _cfg.get("normal_hunt_enabled"):
                            _portal_key = _cfg.get("normal_hunt_portal_key", "Q 포탈 | 라하린 숲")
                        else:
                            _portal_key = _cfg.get("boss_raid_portal_key", "Q 포탈 | 라하린 숲")
                        _pt = _PORTAL_COORDS.get(_portal_key)
                        if _pt:
                            move_cursor_to(_pt[0], _pt[1])
                            time.sleep(0.05)
                            click_image_center(_pt[0], _pt[1])
                            self.log(f"[포탈] 클릭 ({_pt[0]}, {_pt[1]}) - {_portal_key} 진입", "success")
                        ok_hold, _ = self._wait_for_image(IMG.HOLD_CHECK, timeout=5.0, click=False)
                        if ok_hold:
                            self.log(f"[포탈] 영웅이 {_portal_key}에 진입했습니다", "success")
                            # ── 포탈 진입 후 액션 ──
                            _action = _cfg.get(
                                "normal_hunt_action" if _cfg.get("normal_hunt_enabled") else "boss_raid_action", 0
                            )
                            _boss_cfg  = self._get_portal_boss_cfg(_cfg)
                            _use_boss  = _boss_cfg["use_boss"]
                            _respawn_en = _cfg.get(
                                "normal_hunt_respawn" if _cfg.get("normal_hunt_enabled") else "boss_raid_respawn", True
                            )

                            # 보스 우선 토벌: 전체 액션에서 최초 1회 적용
                            if _use_boss and _boss_cfg["boss_priority"] and not self._boss_priority_done:
                                self._boss_priority_done = True
                                self.log(f"[보스 우선] {_boss_cfg['boss_zone']['name']} 바로 이동", "info")
                                _de_p = threading.Event()
                                _se_p = threading.Event()
                                _dt_p = None
                                if _respawn_en:
                                    def _dcl_p(_de=_de_p, _se=_se_p):
                                        _PIX_X, _PIX_Y = 13, 49
                                        while self._running and not _se.is_set():
                                            rgb = _get_pixel_at_client(_PIX_X, _PIX_Y)
                                            if rgb is None: time.sleep(1.0); continue
                                            pr, pg, pb = rgb
                                            if pr == 0 and pg == 0 and pb == 0:
                                                self.log("[사망감지] 영웅 사망 → suicide 재시작", "warn")
                                                self.status("영웅 사망 감지!", RED)
                                                _de.set(); return
                                            time.sleep(1.0)
                                    _dt_p = threading.Thread(target=_dcl_p, daemon=True)
                                    _dt_p.start()
                                _prio_ok = self._run_boss_sequence(_boss_cfg, _de_p, _se_p, _dt_p, _respawn_en)
                                _se_p.set()
                                if _dt_p: _dt_p.join(timeout=2.0)
                                if not _prio_ok:
                                    continue  # 사망 → suicide 루프 처음부터

                            if _action == 0:
                                alive = self._post_portal_instant_hunt(boss_cfg=_boss_cfg)
                                if not alive:
                                    continue  # 사망 → suicide 루프 처음부터
                                if _use_boss: continue  # 보스 완료 → 재시작
                                break
                            elif _action == 1:
                                alive = self._post_portal_zone_hunt(boss_cfg=_boss_cfg)
                                if not alive:
                                    continue  # 오류/사망 → suicide 루프 처음부터
                                continue  # 정상 완료 → suicide 루프 재시작
                            elif _action == 2:
                                alive = self._post_portal_custom_hunt(boss_cfg=_boss_cfg)
                                if not alive:
                                    continue  # 사망 → suicide 루프 처음부터
                                if _use_boss: continue  # 보스 완료 → 재시작
                                break
                        self.log("[포탈] 영웅이 포탈에 진입하지 못했습니다", "warn")
                        continue
                    self.log("[포탈] 포탈 검증 실패 → -suicide 재시도", "warn")
                self.log("[포탈] 이동 미확인 → -suicide 재시도", "warn")
            self.log("[포탈] 정지 화면 미감지 → -suicide 재시도", "warn")

    def _move_to_zone(self, zone: dict, death_event: "threading.Event",
                      stop_event: "threading.Event") -> bool:
        """지정 구역으로 이동 (1차 + 필요 시 2차). 사망/중지 시 False 반환."""
        _step_labels = ["", "2차 ", "3차 "]
        for step, pos_key in enumerate(["pos", "pos2", "pos3"]):
            coords = zone.get(pos_key)
            if not coords:
                continue
            x, y = coords
            label = f"{_step_labels[step]}이동"
            self.log(f"[구역이동] {zone['name']} {label} → ({x}, {y})", "info")
            move_cursor_to(x, y)
            time.sleep(0.05)
            _rc_dl = time.time() + 1.0
            while time.time() < _rc_dl and self._running and not death_event.is_set():
                right_click_image_center(x, y)
                time.sleep(0.25)

            # ── [1단계] 출발 확인: 29.이동.png OR 33.공격.png ──────────────────
            self.log(f"[구역이동][1단계] {label} 출발 확인 시작 (29번 or 33번, 최대 60초)", "info")
            _dep_dl = time.time() + 60.0
            ok29 = False
            dep_by_move = False   # 실제 이동(29.이동.png)으로 출발 확인됐는지 추적
            _dep_iter = 0
            while time.time() < _dep_dl and self._running and not death_event.is_set():
                _dep_iter += 1
                m29, v29, c29, _ = _image_match(IMG.MOVE)
                m33, v33, c33, _ = _image_match(IMG.ATTACK, threshold=0.90)
                if _dep_iter <= 4 or _dep_iter % 8 == 0:
                    self.log(
                        f"[구역이동][1단계] #{_dep_iter} "
                        f"29번={v29:.3f}({'O' if m29 else 'X'}) "
                        f"33번={v33:.3f}({'O' if m33 else 'X'})",
                        "info"
                    )
                if m29:
                    self.log(f"[구역이동][1단계] 29번(이동) 감지 → 출발 확인 (v={v29:.3f}, coords={c29})", "success")
                    ok29 = True; dep_by_move = True; break
                if m33:
                    self.log(f"[구역이동][1단계] 33번(공격) 감지 → 출발 확인(전투중이동) (v={v33:.3f}, coords={c33})", "warn")
                    ok29 = True; break
                time.sleep(0.25)
            if not ok29 or death_event.is_set():
                if death_event.is_set(): return False
                self.log(f"[구역이동][1단계] {label} 29번/33번 모두 미감지 (60초 타임아웃) → 재시도", "warn")
                return False
            self.log(f"[구역이동][1단계] 완료 — dep_by_move={dep_by_move}", "info")

            # ── [2단계] 전투중이동 케이스: 실제 29번 이동 대기 ─────────────────
            if not dep_by_move:
                self.log(f"[구역이동][2단계] 33번으로만 출발 확인 → 실제 이동(29번) 대기 시작 (최대 60초)", "warn")
                _wait_move_dl = time.time() + 60.0
                _wm_iter = 0
                while time.time() < _wait_move_dl and self._running and not death_event.is_set():
                    _wm_iter += 1
                    m29b, v29b, c29b, _ = _image_match(IMG.MOVE)
                    m33b, v33b, _, _ = _image_match(IMG.ATTACK, threshold=0.90)
                    if _wm_iter <= 4 or _wm_iter % 8 == 0:
                        self.log(
                            f"[구역이동][2단계] #{_wm_iter} "
                            f"29번={v29b:.3f}({'O' if m29b else 'X'}) "
                            f"33번={v33b:.3f}({'O' if m33b else 'X'})",
                            "info"
                        )
                    if m29b:
                        self.log(f"[구역이동][2단계] 29번(이동) 감지 → 실제 이동 시작 확인 (v={v29b:.3f}, coords={c29b})", "success")
                        dep_by_move = True; break
                    time.sleep(0.25)
                if not dep_by_move or death_event.is_set():
                    if death_event.is_set(): return False
                    self.log(f"[구역이동][2단계] {label} 전투 후 29번 이동 미감지 (60초) → 재시도", "warn")
                    return False
                self.log(f"[구역이동][2단계] 완료 — 실제 이동 확인됨", "info")

            # ── [3단계] 도착 확인: 30.이동(X).png OR 33.공격.png ──────────────
            self.log(f"[구역이동][3단계] {label} 도착 확인 시작 (30번 or 33번, 최대 60초)", "info")
            _mv_dl = time.time() + 60.0
            ok30 = False
            _arr_iter = 0
            while time.time() < _mv_dl and self._running and not death_event.is_set():
                _arr_iter += 1
                m30, v30, c30, _ = _image_match(IMG.MOVE_X)
                m33, v33, c33, _ = _image_match(IMG.ATTACK, threshold=0.90)
                if _arr_iter <= 8 or _arr_iter % 8 == 0:
                    self.log(
                        f"[구역이동][3단계] #{_arr_iter} "
                        f"30번={v30:.3f}({'O' if m30 else 'X'}) "
                        f"33번={v33:.3f}({'O' if m33 else 'X'})",
                        "info"
                    )
                if m30:
                    self.log(f"[구역이동][3단계] 30번(이동X) 감지 → 도착 확인 (v={v30:.3f}, coords={c30})", "success")
                    ok30 = True; break
                if m33:
                    self.log(f"[구역이동][3단계] 33번(공격) 감지 → 도착 판정(이동중블로킹) (v={v33:.3f}, coords={c33})", "warn")
                    ok30 = True; break
                time.sleep(0.25)

            if death_event.is_set(): return False
            if not ok30:
                self.log(f"[구역이동][3단계] {label} 60초 타임아웃 → 재시도", "warn")
                return False
            self.log(f"[구역이동] {zone['name']} {label} 도착 확인 완료", "success")

        return True

    def _turn_off_auto_hunt(self, stop_event: "threading.Event") -> bool:
        """자동사냥 OFF 시퀀스.
        37번 감지 → 좌클릭 → 13번 감지로 OFF 확인.
        반환: True=성공, False=중단(stop_event 또는 _running=False)"""
        self.log("[자동사냥 해제] 자동사냥 OFF 시도 중...", "info")
        while self._running and not stop_event.is_set():
            ok37, coords37 = self._wait_for_image(
                IMG.HUNT_ON_CHECK, timeout=3.0, click=False, silent=True
            )
            if not self._running or stop_event.is_set():
                return False
            if not ok37:
                continue
            if coords37:
                click_image_center(coords37[0], coords37[1])
            ok13, _ = self._wait_for_image(
                IMG.LOADING_CURSOR, timeout=3.0, click=False, silent=True
            )
            if ok13:
                self.log("[자동사냥 해제] 자동사냥 OFF 확인 완료", "success")
                return True
        return False

    def _boss_fight_macro(self, death_event: "threading.Event",
                          stop_event: "threading.Event",
                          death_thread: "threading.Thread | None") -> bool:
        """보스 전투 매크로.
        33.공격.png 2회 연속 감지(0.25s 간격, 30s 타임아웃) 후 스킬 루프 진입.
        종료 조건: 사망 이벤트, 34.공격(x).png 2회 연속 감지(0.25s, 180s 타임아웃), 또는 타임아웃.
        종료 시 -return 전송 (사망 제외).
        반환: True=정상완료, False=사망(suicide 재시작 필요)"""
        self.log("[보스전투] 33.공격.png 서치 시작 (30초, 2회 연속)", "info")
        self.status("보스 전투 준비 중...", YELLOW)

        # ── Step 1: 33.공격.png 2회 연속 감지 (0.25s 간격, 30s 타임아웃) ──
        deadline33 = time.time() + 30.0
        consec33   = 0
        ok33       = False
        while time.time() < deadline33 and self._running and not death_event.is_set():
            matched, _, _, _ = _image_match(IMG.ATTACK)
            if matched:
                consec33 += 1
                if consec33 >= 2:
                    ok33 = True
                    break
            else:
                consec33 = 0
            time.sleep(0.25)

        if death_event.is_set():
            stop_event.set()
            if death_thread: death_thread.join(timeout=2.0)
            return False

        if not ok33:
            self.log("[보스전투] 33번(공격) 30초 내 미감지 → 전투 스킵", "info")
            stop_event.set()
            if death_thread: death_thread.join(timeout=2.0)
            return True

        self.log("[보스전투] 33번(공격) 2회 연속 감지 → 스킬 루프 시작", "success")
        self.status("보스 전투 중!", YELLOW)

        # ── Step 2~4: 커서 이동(병렬) + 스킬 키 루프 + 34번 감지 ──
        _boss_stop  = threading.Event()
        _skill_keys = [ord('D'), ord('W'), ord('E'), ord('R'), ord('T')]
        _hero_vk    = ord(str(load_config().get("hero_group", 1)))

        def _cursor_loop():
            while not _boss_stop.is_set() and self._running and not death_event.is_set():
                move_cursor_to(50, 75)
                time.sleep(0.1)

        _cursor_thread = threading.Thread(target=_cursor_loop, daemon=True)
        _cursor_thread.start()

        deadline34 = time.time() + 180.0
        consec34   = 0
        ok34       = False
        key_idx    = 0
        while time.time() < deadline34 and self._running and not death_event.is_set():
            vk = _skill_keys[key_idx % len(_skill_keys)]
            # 스킬 키 → 좌클릭 → 영웅 번호 (딜레이 없이 즉시) → 0.1s → 다음 세트
            _press_vk(vk); time.sleep(0.02); _press_vk(vk, keyup=True)
            click_image_center(50, 75)
            _press_vk(_hero_vk); _press_vk(_hero_vk, keyup=True)
            key_idx += 1
            time.sleep(0.1)

            matched34, _, _, _ = _image_match(IMG.ATTACK_X, threshold=0.90)
            if matched34:
                consec34 += 1
                if consec34 >= 2:
                    ok34 = True
                    break
            else:
                consec34 = 0

        _boss_stop.set()
        _cursor_thread.join(timeout=2.0)
        stop_event.set()
        if death_thread: death_thread.join(timeout=2.0)

        if death_event.is_set():
            self.log("[보스전투] 사망 감지 → suicide 루프 재시작", "warn")
            return False

        if ok34:
            self.log("[보스전투] 34번(공격X) 2회 연속 감지 → 보스 전투 종료", "success")
        else:
            self.log("[보스전투] 180초 타임아웃 → 보스 전투 종료", "warn")
        self.status("보스 전투 완료 → 재시작", YELLOW)
        return True

    # ── 보스 설정 헬퍼 ──────────────────────────────────────────────────
    def _get_portal_boss_cfg(self, cfg: dict) -> dict:
        """포탈 키에 따라 보스 관련 설정(보스 여부, 보스 좌표, 타이머, 우선토벌)을 반환."""
        # 액션3 (필드보스) 비활성화 시 보스 없음
        if not cfg.get("normal_hunt_boss_enabled", True):
            return {"use_boss": False, "boss_zone": None, "enabled_bosses": [],
                    "boss_timer_on": False, "boss_timer_sec": 60.0, "boss_priority": False}

        # boss_exit: 보스맵 → 필드맵 복귀 좌표 (별도 서브맵인 경우). None = 같은 맵
        _BOSS_ZONES_Q = [
            {"key": "nh_zone_boss",       "name": "도적단장 - 칼레인",    "pos": (70,  884), "pos2": (237, 834), "pos3": None,       "boss_exit": {"pos": (237, 839), "pos2": None}},
            {"key": "nh_q_boss_kingcrab", "name": "백년 묵은 킹크랩",     "pos": (76,  881), "pos2": (212, 869), "pos3": None,       "boss_exit": {"pos": (212, 874), "pos2": None}},
            {"key": "nh_q_boss_giant",    "name": "늪의 거인",             "pos": (76,  881), "pos2": (211, 864), "pos3": (235, 863), "boss_exit": {"pos": (234, 872), "pos2": (212, 874)}},
            {"key": "nh_q_boss_pap",      "name": "잊혀진 수호자 - 파프", "pos": (69,  873), "pos2": None,       "pos3": None,       "boss_exit": None},
        ]
        _BOSS_ZONE_W = {"name": "매직웨건", "pos": (29, 912), "pos2": (234, 849), "boss_exit": {"pos": (234, 855), "pos2": None}}
        _BOSS_ZONES_E = [
            {"key": "nh_e_boss_maureus",  "name": "마우레우스",        "pos": (28, 942), "pos2": (49, 986),  "pos3": None,       "boss_exit": {"pos": (49, 994),  "pos2": None}, "shortcuts": {"nh_e_boss_tarod":   {"pos": (49, 980), "pos2": (49, 972)}}},
            {"key": "nh_e_boss_tarod",    "name": "타로드",            "pos": (28, 942), "pos2": (49, 980),  "pos3": (49, 972),  "boss_exit": {"pos": (49, 994),  "pos2": None}, "shortcuts": {"nh_e_boss_maureus": {"pos": (49, 979), "pos2": (49, 980)}}},
            {"key": "nh_e_boss_colossus", "name": "바위거인 콜로서스", "pos": (49, 934), "pos2": (233, 883), "pos3": None,       "boss_exit": {"pos": (233, 887), "pos2": None}},
            {"key": "nh_e_boss_tulak",    "name": "사도: 툴'락",       "pos": (53, 938), "pos2": (65, 934),  "pos3": None,       "boss_exit": {"pos": (52, 938),  "pos2": None}},
        ]
        _BOSS_ZONES_R = [
            {"key": "nh_r_boss_hedan",    "name": "보급장교 헤단",   "pos": ( 94, 835), "pos2": (213, 883), "pos3": None, "boss_exit": {"pos": (212, 888), "pos2": None}},
            {"key": "nh_r_boss_thanatos", "name": "사신 - 타나토스", "pos": (120, 857), "pos2": (279, 850), "pos3": None, "boss_exit": {"pos": (279, 857), "pos2": None}},
        ]
        _BOSS_ZONES_A = [
            {"key": "nh_a_boss_bx485", "name": "BX-485",          "pos": (133, 878), "pos2": None, "pos3": None, "boss_exit": None},
            {"key": "nh_a_boss_ivan",  "name": "엔지니어 - 이반", "pos": (133, 866), "pos2": None, "pos3": None, "boss_exit": None},
        ]
        _BOSS_ZONES_S = [
            {"key": "nh_s_boss_callis", "name": "집행자 캘리스", "pos": (120, 909), "pos2": None,       "pos3": None, "boss_exit": None},
            {"key": "nh_s_boss_kalipa", "name": "마룡: 칼리파",  "pos": (120, 917), "pos2": (256, 848), "pos3": None, "boss_exit": {"pos": (256, 856), "pos2": None}},
        ]
        _BOSS_ZONES_D = [
            {"key": "nh_d_boss_klak",   "name": "클락",   "pos": (127, 941), "pos2": None,       "pos3": None, "boss_exit": None},
            {"key": "nh_d_boss_mirdon", "name": "미르돈", "pos": (127, 954), "pos2": None,       "pos3": None, "boss_exit": None},
            {"key": "nh_d_boss_rex",    "name": "렉스",   "pos": (142, 942), "pos2": (253, 864), "pos3": None, "boss_exit": {"pos": (263, 871), "pos2": None}},
        ]
        _BOSS_ZONES_F = [
            {"key": "nh_f_boss_doombaou", "name": "둠바우", "pos": (186, 852), "pos2": None, "pos3": None, "boss_exit": None},
        ]
        _BOSS_ZONES_Z = [
            {"key": "nh_z_boss_flame", "name": "플레임", "pos": (160, 867), "pos2": None, "pos3": None, "boss_exit": None},
        ]

        is_nh      = cfg.get("normal_hunt_enabled", False)
        portal_key = cfg.get(
            "normal_hunt_portal_key" if is_nh else "boss_raid_portal_key",
            "Q 포탈 | 라하린 숲"
        )

        use_boss       = False
        boss_zone      = None
        enabled_bosses: list = []
        _timer_key     = ""
        _timer_sec_key = ""
        _priority_key  = ""
        _no_return_key = ""

        if portal_key == "E 포탈 | 어둠얼음성채":
            _order = cfg.get("nh_e_boss_order", [])
            enabled_bosses = sorted(
                [b for b in _BOSS_ZONES_E if cfg.get(b["key"], False)],
                key=lambda b: _order.index(b["key"]) if b["key"] in _order else len(_order),
            )
            use_boss       = bool(enabled_bosses)
            boss_zone      = enabled_bosses[0] if enabled_bosses else _BOSS_ZONES_E[0]
            _timer_key     = "nh_e_boss_timer"
            _timer_sec_key = "nh_e_boss_timer_sec"
            _priority_key  = "nh_e_boss_priority"
            _no_return_key = "nh_e_boss_no_return"
        elif portal_key == "R 포탈 | 버려진 고성":
            _order = cfg.get("nh_r_boss_order", [])
            enabled_bosses = sorted(
                [b for b in _BOSS_ZONES_R if cfg.get(b["key"], False)],
                key=lambda b: _order.index(b["key"]) if b["key"] in _order else len(_order),
            )
            use_boss       = bool(enabled_bosses)
            boss_zone      = enabled_bosses[0] if enabled_bosses else _BOSS_ZONES_R[0]
            _timer_key     = "nh_r_boss_timer"
            _timer_sec_key = "nh_r_boss_timer_sec"
            _priority_key  = "nh_r_boss_priority"
            _no_return_key = "nh_r_boss_no_return"
        elif portal_key == "A 포탈 | 바위협곡":
            _order = cfg.get("nh_a_boss_order", [])
            enabled_bosses = sorted(
                [b for b in _BOSS_ZONES_A if cfg.get(b["key"], False)],
                key=lambda b: _order.index(b["key"]) if b["key"] in _order else len(_order),
            )
            use_boss       = bool(enabled_bosses)
            boss_zone      = enabled_bosses[0] if enabled_bosses else _BOSS_ZONES_A[0]
            _timer_key     = "nh_a_boss_timer"
            _timer_sec_key = "nh_a_boss_timer_sec"
            _priority_key  = "nh_a_boss_priority"
            _no_return_key = "nh_a_boss_no_return"
        elif portal_key == "S 포탈 | 바람의 협곡":
            _order = cfg.get("nh_s_boss_order", [])
            enabled_bosses = sorted(
                [b for b in _BOSS_ZONES_S if cfg.get(b["key"], False)],
                key=lambda b: _order.index(b["key"]) if b["key"] in _order else len(_order),
            )
            use_boss       = bool(enabled_bosses)
            boss_zone      = enabled_bosses[0] if enabled_bosses else _BOSS_ZONES_S[0]
            _timer_key     = "nh_s_boss_timer"
            _timer_sec_key = "nh_s_boss_timer_sec"
            _priority_key  = "nh_s_boss_priority"
            _no_return_key = "nh_s_boss_no_return"
        elif portal_key == "D 포탈 | 시계태엽 공장":
            _order = cfg.get("nh_d_boss_order", [])
            enabled_bosses = sorted(
                [b for b in _BOSS_ZONES_D if cfg.get(b["key"], False)],
                key=lambda b: _order.index(b["key"]) if b["key"] in _order else len(_order),
            )
            use_boss       = bool(enabled_bosses)
            boss_zone      = enabled_bosses[0] if enabled_bosses else _BOSS_ZONES_D[0]
            _timer_key     = "nh_d_boss_timer"
            _timer_sec_key = "nh_d_boss_timer_sec"
            _priority_key  = "nh_d_boss_priority"
            _no_return_key = "nh_d_boss_no_return"
        elif portal_key == "F 포탈 | 속삭임의 숲":
            enabled_bosses = [b for b in _BOSS_ZONES_F if cfg.get(b["key"], False)]
            use_boss       = bool(enabled_bosses)
            boss_zone      = enabled_bosses[0] if enabled_bosses else _BOSS_ZONES_F[0]
            _timer_key     = "nh_f_boss_timer"
            _timer_sec_key = "nh_f_boss_timer_sec"
            _priority_key  = "nh_f_boss_priority"
            _no_return_key = "nh_f_boss_no_return"
        elif portal_key == "Z 포탈 | 이그니스영역":
            enabled_bosses = [b for b in _BOSS_ZONES_Z if cfg.get(b["key"], False)]
            use_boss       = bool(enabled_bosses)
            boss_zone      = enabled_bosses[0] if enabled_bosses else _BOSS_ZONES_Z[0]
            _timer_key     = "nh_z_boss_timer"
            _timer_sec_key = "nh_z_boss_timer_sec"
            _priority_key  = "nh_z_boss_priority"
            _no_return_key = "nh_z_boss_no_return"
        elif portal_key == "X 포탈 | 정령계":
            use_boss = False
            _timer_key = "nh_x_boss_timer"; _timer_sec_key = "nh_x_boss_timer_sec"
            _priority_key = "nh_x_boss_priority"; _no_return_key = "nh_x_boss_no_return"
        elif portal_key == "W 포탈 | 아스탈 요새":
            use_boss       = cfg.get("nh_w_zone_boss", False)
            boss_zone      = _BOSS_ZONE_W
            enabled_bosses = [_BOSS_ZONE_W] if use_boss else []
            _timer_key     = "nh_w_boss_timer"
            _timer_sec_key = "nh_w_boss_timer_sec"
            _priority_key  = "nh_w_boss_priority"
            _no_return_key = "nh_w_boss_no_return"
        else:  # Q 포탈 | 라하린 숲
            _order = cfg.get("nh_boss_order", [])
            enabled_bosses = sorted(
                [b for b in _BOSS_ZONES_Q if cfg.get(b["key"], False)],
                key=lambda b: _order.index(b["key"]) if b["key"] in _order else len(_order),
            )
            use_boss       = bool(enabled_bosses)
            boss_zone      = enabled_bosses[0] if enabled_bosses else _BOSS_ZONES_Q[0]
            _timer_key     = "nh_boss_timer"
            _timer_sec_key = "nh_boss_timer_sec"
            _priority_key  = "nh_boss_priority"
            _no_return_key = "nh_boss_no_return"

        # 마지막 보스의 boss_exit 추출 (필드 복귀 시 사용)
        _boss_exit = enabled_bosses[-1].get("boss_exit") if enabled_bosses else None

        return {
            "use_boss":       use_boss,
            "boss_zone":      boss_zone,
            "enabled_bosses": enabled_bosses,
            "boss_timer_on":  cfg.get(_timer_key,     False) if _timer_key else False,
            "boss_timer_sec": cfg.get(_timer_sec_key, 60.0)  if _timer_sec_key else 60.0,
            "boss_priority":  cfg.get(_priority_key,  False) if _priority_key else False,
            "boss_no_return": cfg.get(_no_return_key, False) if _no_return_key else False,
            "boss_exit":      _boss_exit,
        }

    def _fight_boss_and_extras(self, boss_cfg: dict, death_event: "threading.Event",
                               stop_event: "threading.Event",
                               death_thread: "threading.Thread | None",
                               respawn_enabled: bool) -> bool:
        """현재 위치에서 보스 전투 + 추가 보스 순차 방문 (이동 없이 즉시 전투 시작).
        보스 간 이동 시 현재 보스의 boss_exit가 있으면 서브맵 출구 경유 후 다음 보스로 이동.
        반환: True=완료, False=사망"""
        bosses = boss_cfg["enabled_bosses"]

        # ── 첫 번째 보스: 별도 _se0 + death_thread=None → main death_thread 보호 ──
        # _boss_fight_macro 는 종료 시 stop_event.set() + death_thread.join() 을 호출하므로
        # main stop_event/death_thread 를 직접 넘기면 사망 감지 스레드가 조기 종료된다.
        _se0 = threading.Event()
        if not self._boss_fight_macro(death_event, _se0, None):
            # 사망 → main death_thread 정리 후 반환
            stop_event.set()
            if death_thread: death_thread.join(timeout=2.0)
            return False

        for i, extra in enumerate(bosses[1:], 1):
            if not self._running:
                return True  # death_thread 정리는 caller 담당

            # 추가 보스마다 전용 사망감지 스레드 생성
            _de2, _se2 = threading.Event(), threading.Event()
            _dt2 = None
            if respawn_enabled:
                def _dcl(_de=_de2, _se=_se2):
                    _PIX_X, _PIX_Y = 13, 49
                    while self._running and not _se.is_set():
                        rgb = _get_pixel_at_client(_PIX_X, _PIX_Y)
                        if rgb is None: time.sleep(1.0); continue
                        pr, pg, pb = rgb
                        if pr == 0 and pg == 0 and pb == 0:
                            self.log("[사망감지] 영웅 사망 → suicide 재시작", "warn")
                            self.status("영웅 사망 감지!", RED)
                            _de.set(); return
                        time.sleep(1.0)
                _dt2 = threading.Thread(target=_dcl, daemon=True)
                _dt2.start()

            # 보스 간 이동: main death_event 로 체크 (main death_thread 가 살아있으므로)
            _prev      = bosses[i - 1]
            _next_key  = extra.get("key", "")
            _shortcuts = _prev.get("shortcuts", {})
            if _next_key in _shortcuts:
                _sc = _shortcuts[_next_key]
                _sc_zone = {"name": f"{_prev['name']} → {extra['name']} 숏컷", "pos": _sc["pos"], "pos2": _sc.get("pos2")}
                self.log(f"[보스이동] {_prev['name']} → {extra['name']} 숏컷 경로 (서브맵 출구 스킵)", "info")
                if not self._move_to_zone(_sc_zone, death_event, _se2):
                    _se2.set()
                    if _dt2: _dt2.join(timeout=2.0)
                    stop_event.set()
                    if death_thread: death_thread.join(timeout=2.0)
                    return False
            else:
                _prev_exit = _prev.get("boss_exit")
                if _prev_exit:
                    _exit_zone = {"name": f"{_prev['name']} 출구", "pos": _prev_exit["pos"], "pos2": _prev_exit.get("pos2")}
                    self.log(f"[보스이동] {_prev['name']} 서브맵 출구 경유 → {extra['name']}", "info")
                    if not self._move_to_zone(_exit_zone, death_event, _se2):
                        _se2.set()
                        if _dt2: _dt2.join(timeout=2.0)
                        stop_event.set()
                        if death_thread: death_thread.join(timeout=2.0)
                        return False
                if not self._move_to_zone(extra, death_event, _se2):
                    _se2.set()
                    if _dt2: _dt2.join(timeout=2.0)
                    stop_event.set()
                    if death_thread: death_thread.join(timeout=2.0)
                    return False

            if not self._boss_fight_macro(_de2, _se2, _dt2):
                # 추가 보스 전투 중 사망 → main death_thread 정리
                stop_event.set()
                if death_thread: death_thread.join(timeout=2.0)
                return False

        # 모든 보스 처치 완료 → death_thread 정리는 caller 담당
        return True

    def _run_boss_sequence(self, boss_cfg: dict, death_event: "threading.Event",
                           stop_event: "threading.Event",
                           death_thread: "threading.Thread | None",
                           respawn_enabled: bool) -> bool:
        """보스 위치로 이동 → 전투 → 추가 보스 순차 방문.
        반환: True=완료, False=사망"""
        boss_zone = boss_cfg["boss_zone"]
        if not self._move_to_zone(boss_zone, death_event, stop_event):
            stop_event.set()
            if death_thread: death_thread.join(timeout=2.0)
            return False
        return self._fight_boss_and_extras(boss_cfg, death_event, stop_event, death_thread, respawn_enabled)

    def _post_portal_zone_hunt(self, boss_cfg: dict) -> bool:
        """포탈 진입 후 특정 구역으로 이동 후 자동사냥 (액션 1).
        반환: True=정상완료, False=오류/사망(suicide 재시작 필요)"""
        _ZONES_Q = [
            {"name": "오래된 숲의 정령 (아래)", "pos": (34,  887), "pos2": None},
            {"name": "오래된 숲의 정령 (위)",   "pos": (36,  876), "pos2": None},
            {"name": "동굴 왕 두꺼비",          "pos": (35,  867), "pos2": None},
            {"name": "토끼 굴",                 "pos": (28,  865), "pos2": (211, 834), "exit_pos": (208, 828)},
            {"name": "그을음 도적단 부단장",    "pos": (67,  887), "pos2": None},
        ]
        _ZONES_W = [
            {"name": "경비대장 로웰",           "pos": (62,  905), "pos2": None},
            {"name": "무쇠발톱",                "pos": (58,  918), "pos2": None},
            {"name": "TX-005",                  "pos": (48,  921), "pos2": None},
            {"name": "드워프, 중갑차, 정예병",  "pos": (41,  914), "pos2": None},
        ]
        _ZONES_E = [
            {"name": "바레스",                 "pos": (38, 937), "pos2": None},
            {"name": "오래된 고대유적 수호자", "pos": (46, 936), "pos2": None},
            {"name": "거울 여왕의 파편",       "pos": (32, 944), "pos2": None},
        ]
        _ZONES_R = [
            {"name": "(LT)제국기사의 망령", "pos": ( 96, 841), "pos2": None},
            {"name": "(RT)제국기사의 망령", "pos": (112, 834), "pos2": None},
            {"name": "옛 수비대장 펠릭스",  "pos": (102, 846), "pos2": None},
            {"name": "옛 집행관 라나",      "pos": (126, 832), "pos2": None},
        ]
        _ZONES_A = [
            {"name": "(7시) 고블린",              "pos": (128, 886), "pos2": None},
            {"name": "(5시) 고블린",              "pos": (137, 886), "pos2": None},
            {"name": "(10시) 고블린",             "pos": (126, 871), "pos2": None},
            {"name": "(2시) 고블린",              "pos": (139, 870), "pos2": None},
            {"name": "깊은 동굴 - 거대한 숲 거인", "pos": (144, 878), "pos2": (276, 885), "exit_pos": (286, 885)},
        ]
        _ZONES_S = [
            {"name": "(LT) 바람의 정령",      "pos": (101, 908), "pos2": None},
            {"name": "(RT) 바람의 정령",      "pos": (111, 900), "pos2": None},
            {"name": "중급 바람의 정령 윈디", "pos": ( 99, 912), "pos2": None},
            {"name": "검은가죽 드루이드",     "pos": (115, 918), "pos2": None},
            {"name": "동굴 깊은 곳",          "pos": (123, 909), "pos2": (277, 898), "exit_pos": (274, 894)},
            {"name": "상급 바람의 정령 실프", "pos": (123, 909), "pos2": (280, 902), "exit_pos": (274, 894)},
        ]
        _ZONES_D = [
            {"name": "(LT) 마정석 골렘", "pos": (117, 951), "pos2": None},
            {"name": "(RT) 마정석 골렘", "pos": (131, 948), "pos2": None},
        ]
        _ZONES_F = [
            {"name": "(위) 강철집게",   "pos": (183, 837), "pos2": None},
            {"name": "(아래) 강철집게", "pos": (167, 851), "pos2": None},
        ]
        _ZONES_Z = [
            {"name": "(입구) 용암굴", "pos": (178, 883), "pos2": None},
            {"name": "(위) 용암굴",   "pos": (178, 869), "pos2": None},
            {"name": "(LT) 용암굴",   "pos": (164, 870), "pos2": None},
            {"name": "(아래) 용암굴", "pos": (160, 881), "pos2": None},
        ]
        _ZONES_X = [
            {"name": "(LT) 정령계", "pos": (163, 925), "pos2": None},
            {"name": "(RT) 정령계", "pos": (183, 921), "pos2": None},
        ]

        cfg        = load_config()
        is_nh      = cfg.get("normal_hunt_enabled", False)
        portal_key = cfg.get("normal_hunt_portal_key" if is_nh else "boss_raid_portal_key", "Q 포탈 | 라하린 숲")

        # ── 포탈별 구역/zone_idx_key 선택 ──
        _ZONE_MAP = {
            "W 포탈 | 아스탈 요새":   (_ZONES_W, "nh_w_zone_idx"),
            "E 포탈 | 어둠얼음성채":  (_ZONES_E, "nh_e_zone_idx"),
            "R 포탈 | 버려진 고성":   (_ZONES_R, "nh_r_zone_idx"),
            "A 포탈 | 바위협곡":      (_ZONES_A, "nh_a_zone_idx"),
            "S 포탈 | 바람의 협곡":   (_ZONES_S, "nh_s_zone_idx"),
            "D 포탈 | 시계태엽 공장": (_ZONES_D, "nh_d_zone_idx"),
            "F 포탈 | 속삭임의 숲":   (_ZONES_F, "nh_f_zone_idx"),
            "Z 포탈 | 이그니스영역":  (_ZONES_Z, "nh_z_zone_idx"),
            "X 포탈 | 정령계":        (_ZONES_X, "nh_x_zone_idx"),
        }
        _ZONES, _zone_idx_key = _ZONE_MAP.get(portal_key, (_ZONES_Q, "nh_zone_idx"))

        # ── boss_cfg에서 보스 설정 추출 ──
        use_boss       = boss_cfg["use_boss"]
        boss_timer_on  = boss_cfg["boss_timer_on"]
        boss_timer_sec = boss_cfg["boss_timer_sec"]
        _BOSS_ZONE     = boss_cfg["boss_zone"]
        _respawn_enabled = cfg.get("normal_hunt_respawn" if is_nh else "boss_raid_respawn", True)

        # ── 구역 선택: 보스(타이머 없음) → 보스 구역, 그 외 → 필드 구역 ──
        if use_boss and not boss_timer_on:
            zone = _BOSS_ZONE
        else:
            zone_idx = cfg.get(_zone_idx_key if is_nh else "br_zone_idx", 0)
            zone_idx = max(0, min(zone_idx, len(_ZONES) - 1))
            zone = _ZONES[zone_idx]

        name = zone["name"]
        x, y = zone["pos"]
        pos2 = zone["pos2"]

        # ── 포탈 진입 직후 사망 감지 시작 ──
        _death_event = threading.Event()
        _stop_event  = threading.Event()

        def _death_check_loop():
            _PIX_X, _PIX_Y = 13, 49
            self.log("[사망감지] 픽셀 감시 시작 (40번 X:13 Y:49)", "info")
            while self._running and not _stop_event.is_set():
                rgb = _get_pixel_at_client(_PIX_X, _PIX_Y)
                if rgb is None:
                    time.sleep(1.0)
                    continue
                pr, pg, pb = rgb
                _is_black   = (pr == 0 and pg == 0 and pb == 0)
                _brightness = max(pr, pg, pb) / 255.0
                _bar        = "█" * int(_brightness * 10) + "░" * (10 - int(_brightness * 10))
                # 살아있음 → 상태바에만 표시 (로그 패널 덮어쓰기 방지)
                self.status(f"사망감지 ({pr},{pg},{pb}) [{_bar}]",
                            RED if _is_black else GREEN)
                if _is_black:
                    self.log(
                        f"[사망감지] 40번 픽셀 ({pr:3d},{pg:3d},{pb:3d}) [{_bar}] → 사망!",
                        "warn"
                    )
                    self.log("[사망감지] 영웅 사망 확정 → suicide 루프 재시작", "warn")
                    self.status("영웅 사망 감지!", RED)
                    _death_event.set()
                    return
                time.sleep(1.0)

        _death_thread = None
        if _respawn_enabled:
            _death_thread = threading.Thread(target=_death_check_loop, daemon=True)
            _death_thread.start()

        # ── 보스 타이머는 구역 도착 후 루프 내에서 시작 ──
        _boss_event = threading.Event()
        _bt = None

        self.log(f"[구역이동] {name} → ({x}, {y}) 이동 시작", "info")
        self.status(f"구역 이동 중: {name}", YELLOW)

        # ── 마우스 이동 후 1초간 0.25초마다 우클릭 (최대 4회) ──
        move_cursor_to(x, y)
        time.sleep(0.05)
        _rc_deadline = time.time() + 1.0
        while time.time() < _rc_deadline and self._running and not _death_event.is_set():
            right_click_image_center(x, y)
            time.sleep(0.25)

        # ── 29.이동.png 서치 (타임아웃 1초) — 이동 시작 확인 ──
        ok29, _ = self._wait_for_image(IMG.MOVE, timeout=1.0, click=False)
        if not ok29 or _death_event.is_set():
            _stop_event.set()
            if _death_thread: _death_thread.join(timeout=2.0)
            if _death_event.is_set():
                return False
            self.log("[구역이동] 29번 이동 미감지 → 매크로 오류, 재시도", "warn")
            return False

        self.log("[구역이동] 이동 확인 → 도착 대기 중...", "info")

        # ── 30.이동(X).png 서치 (타임아웃 60초, 사망 감지 시 즉시 중단) ──
        _move_deadline = time.time() + 60.0
        ok30 = False
        while time.time() < _move_deadline and self._running and not _death_event.is_set():
            matched, _, _, _ = _image_match(IMG.MOVE_X)
            if matched:
                ok30 = True
                break
            time.sleep(0.25)

        if _death_event.is_set():
            _stop_event.set()
            if _death_thread: _death_thread.join(timeout=2.0)
            return False
        if not ok30:
            _stop_event.set()
            if _death_thread: _death_thread.join(timeout=2.0)
            self.log("[구역이동] 60초 이동 타임아웃 → 매크로 오류, 재시도", "warn")
            return False

        # ── 2차 이동 (해당 구역에 추가 이동이 필요한 경우) ──
        if pos2 and not _death_event.is_set():
            x2, y2 = pos2
            self.log(f"[구역이동] {name} 2차 이동 → ({x2}, {y2})", "info")
            move_cursor_to(x2, y2)
            time.sleep(0.05)
            _rc_deadline2 = time.time() + 1.0
            while time.time() < _rc_deadline2 and self._running and not _death_event.is_set():
                right_click_image_center(x2, y2)
                time.sleep(0.25)

            ok29b, _ = self._wait_for_image(IMG.MOVE, timeout=1.0, click=False)
            if not ok29b or _death_event.is_set():
                _stop_event.set()
                if _death_thread: _death_thread.join(timeout=2.0)
                if _death_event.is_set():
                    return False
                self.log("[구역이동] 2차 이동 29번 미감지 → 매크로 오류, 재시도", "warn")
                return False

            self.log("[구역이동] 2차 이동 확인 → 도착 대기 중...", "info")

            _move_deadline2 = time.time() + 60.0
            ok30b = False
            while time.time() < _move_deadline2 and self._running and not _death_event.is_set():
                matched, _, _, _ = _image_match(IMG.MOVE_X)
                if matched:
                    ok30b = True
                    break
                time.sleep(0.25)

            if _death_event.is_set():
                _stop_event.set()
                if _death_thread: _death_thread.join(timeout=2.0)
                return False
            if not ok30b:
                _stop_event.set()
                if _death_thread: _death_thread.join(timeout=2.0)
                self.log("[구역이동] 2차 이동 60초 타임아웃 → 매크로 오류, 재시도", "warn")
                return False

            _next = "보스 매크로 시작" if use_boss else "자동사냥 시작"
            self.log(f"[구역이동] {name} 2차 도착 확인 → {_next}", "success")

        _next = "보스 매크로 시작" if use_boss else "자동사냥 시작"
        self.log(f"[구역이동] {name} 도착 확인 → {_next}", "success")

        # ── 필드 자동사냥 ↔ 보스 순환 루프 ──
        if boss_timer_on and use_boss:
            _boss_no_return = boss_cfg.get("boss_no_return", False)
            result = True
            _first_iter = True
            while self._running and not _death_event.is_set():
                # 2번째 사이클부터: 보스 처치 후 필드 구역으로 복귀 이동
                if not _first_iter:
                    self.log(f"[보스복귀] 필드 구역 복귀: {zone['name']}", "info")
                    self.status(f"필드 복귀 중: {zone['name']}", YELLOW)
                    if not self._move_to_zone(zone, _death_event, _stop_event):
                        _stop_event.set()
                        if _death_thread: _death_thread.join(timeout=2.0)
                        return False
                _first_iter = False

                # 보스 타이머 시작 (구역 도착 후)
                _boss_event = threading.Event()
                def _boss_timer_fn(_be=_boss_event):
                    self.log(f"[보스 타이머] {boss_timer_sec:.3f}초 후 보스 이동 예정", "info")
                    deadline = time.time() + boss_timer_sec
                    while time.time() < deadline:
                        if not self._running or _death_event.is_set() or _stop_event.is_set():
                            return
                        time.sleep(0.25)
                    if self._running and not _death_event.is_set() and not _stop_event.is_set():
                        self.log("[보스 타이머] 타이머 만료 → 자동사냥 해제 후 보스 이동", "warn")
                        _be.set()
                _bt = threading.Thread(target=_boss_timer_fn, daemon=True)
                _bt.start()

                result = self._post_portal_instant_hunt(
                    death_event=_death_event, stop_event=_stop_event,
                    death_thread=_death_thread, respawn_enabled=_respawn_enabled,
                    boss_event=_boss_event,
                )
                if _bt: _bt.join(timeout=2.0)

                # 타이머 미만료 (세이브 인터벌·중지·사망) → 루프 탈출
                if not _boss_event.is_set() or _death_event.is_set() or not self._running:
                    break

                # 보스 타이머 만료 → 자동사냥 OFF → (출구 경유) → 보스 이동 + 전투
                if not self._turn_off_auto_hunt(_stop_event):
                    _stop_event.set()
                    if _death_thread: _death_thread.join(timeout=2.0)
                    return False
                _exit_pos = zone.get("exit_pos")
                if _exit_pos and not _death_event.is_set():
                    _exit_zone = {"name": f"{zone['name']} 출구", "pos": _exit_pos, "pos2": None}
                    self.log(f"[구역이동] {zone['name']} 출구 경유 → {_exit_pos}", "info")
                    if not self._move_to_zone(_exit_zone, _death_event, _stop_event):
                        _stop_event.set()
                        if _death_thread: _death_thread.join(timeout=2.0)
                        return False

                boss_ok = self._run_boss_sequence(boss_cfg, _death_event, _stop_event, _death_thread, _respawn_enabled)
                if not boss_ok:
                    # _fight_boss_and_extras 내 실패 경로에서 이미 death_thread 정리됨
                    return False  # 사망

                # boss_no_return=False: 기존 동작 → suicide 재시작
                if not _boss_no_return:
                    _stop_event.set()
                    if _death_thread: _death_thread.join(timeout=2.0)
                    return True

                # boss_no_return=True: 보스 출구 경유 후 필드 복귀 루프
                _boss_exit = boss_cfg.get("boss_exit")
                if _boss_exit and not _death_event.is_set():
                    _be_zone = {"name": "보스 출구", "pos": _boss_exit["pos"], "pos2": _boss_exit.get("pos2")}
                    self.log("[보스복귀] 보스 서브맵 출구 경유", "info")
                    self.status("보스 출구 이동 중...", YELLOW)
                    if not self._move_to_zone(_be_zone, _death_event, _stop_event):
                        _stop_event.set()
                        if _death_thread: _death_thread.join(timeout=2.0)
                        return False
                # 루프 상단에서 _move_to_zone(zone)으로 필드 복귀

            _stop_event.set()
            if _death_thread: _death_thread.join(timeout=2.0)
            return False if _death_event.is_set() else result

        # 보스 구역 도착 → 현재 위치에서 바로 보스 전투 (이미 이동 완료)
        if use_boss:
            result = self._fight_boss_and_extras(boss_cfg, _death_event, _stop_event, _death_thread, _respawn_enabled)
            _stop_event.set()
            if _death_thread: _death_thread.join(timeout=2.0)
            return result

        return self._post_portal_instant_hunt(
            death_event=_death_event, stop_event=_stop_event,
            death_thread=_death_thread, respawn_enabled=_respawn_enabled
        )

    def _post_portal_custom_hunt(self, boss_cfg: "dict | None" = None) -> bool:
        """포탈 진입 후 커스텀 좌표 순서대로 이동 후 자동사냥 (액션 2).
        boss_cfg가 있으면 waypoint 도착 후 보스 로직도 처리.
        반환: True=정상완료, False=사망(suicide 재시작 필요)"""
        cfg   = load_config()
        is_nh = cfg.get("normal_hunt_enabled", False)
        raw   = cfg.get("nh_custom_coords" if is_nh else "br_custom_coords", [])

        # (0, 0) 제외, 유효한 경유지만 추출
        waypoints = [(c[0], c[1]) for c in raw if len(c) >= 2 and (c[0] != 0 or c[1] != 0)]

        if not waypoints:
            self.log("[커스텀이동] 유효한 좌표 없음 → 즉시 자동사냥으로 대체", "warn")
            return self._post_portal_instant_hunt()

        _death_event = threading.Event()
        _stop_event  = threading.Event()
        _respawn_enabled = cfg.get(
            "normal_hunt_respawn" if is_nh else "boss_raid_respawn", True
        )

        def _death_check_loop():
            _PIX_X, _PIX_Y = 13, 49
            self.log("[사망감지] 픽셀 감시 시작 (40번 X:13 Y:49)", "info")
            while self._running and not _stop_event.is_set():
                rgb = _get_pixel_at_client(_PIX_X, _PIX_Y)
                if rgb is None:
                    time.sleep(1.0)
                    continue
                pr, pg, pb = rgb
                _is_black   = (pr == 0 and pg == 0 and pb == 0)
                _brightness = max(pr, pg, pb) / 255.0
                _bar        = "█" * int(_brightness * 10) + "░" * (10 - int(_brightness * 10))
                # 살아있음 → 상태바에만 표시 (로그 패널 덮어쓰기 방지)
                self.status(f"사망감지 ({pr},{pg},{pb}) [{_bar}]",
                            RED if _is_black else GREEN)
                if _is_black:
                    self.log(
                        f"[사망감지] 40번 픽셀 ({pr:3d},{pg:3d},{pb:3d}) [{_bar}] → 사망!",
                        "warn"
                    )
                    self.log("[사망감지] 영웅 사망 확정 → suicide 루프 재시작", "warn")
                    self.status("영웅 사망 감지!", RED)
                    _death_event.set()
                    return
                time.sleep(1.0)

        if _respawn_enabled:
            _death_thread = threading.Thread(target=_death_check_loop, daemon=True)
            _death_thread.start()
        else:
            _death_thread = None

        # 경유지 순서대로 이동
        for idx, (x, y) in enumerate(waypoints, 1):
            if not self._running or _death_event.is_set():
                _stop_event.set()
                if _death_thread:
                    _death_thread.join(timeout=2.0)
                return False
            self.log(f"[커스텀이동] 경유지 {idx}/{len(waypoints)} → ({x}, {y})", "info")
            self.status(f"커스텀 경유지 {idx} 이동 중", YELLOW)
            zone = {"name": f"커스텀 경유지 {idx}", "pos": (x, y), "pos2": None}
            if not self._move_to_zone(zone, _death_event, _stop_event):
                _stop_event.set()
                if _death_thread:
                    _death_thread.join(timeout=2.0)
                return False

        self.log("[커스텀이동] 마지막 경유지 도착", "success")

        # ── 보스 처리 (boss_cfg 있을 때) ──
        if boss_cfg and boss_cfg["use_boss"]:
            use_boss      = boss_cfg["use_boss"]
            boss_timer_on = boss_cfg["boss_timer_on"]
            boss_timer_sec = boss_cfg["boss_timer_sec"]
            if not boss_timer_on:
                # 타이머 없음 → 즉시 보스 이동 + 전투
                self.log("[커스텀이동] 보스 이동 시작", "info")
                result = self._run_boss_sequence(boss_cfg, _death_event, _stop_event, _death_thread, _respawn_enabled)
                _stop_event.set()
                if _death_thread: _death_thread.join(timeout=2.0)
                return result
            else:
                # 타이머 있음 → 자동사냥 후 타이머 만료 시 보스
                _boss_event = threading.Event()
                def _boss_timer():
                    self.log(f"[보스 타이머] {boss_timer_sec:.3f}초 후 보스 이동 예정", "info")
                    _dl = time.time() + boss_timer_sec
                    while time.time() < _dl:
                        if not self._running or _death_event.is_set() or _stop_event.is_set(): return
                        time.sleep(0.25)
                    if self._running and not _death_event.is_set() and not _stop_event.is_set():
                        self.log("[보스 타이머] 타이머 만료 → 자동사냥 해제 후 보스 이동", "warn")
                        _boss_event.set()
                _bt = threading.Thread(target=_boss_timer, daemon=True)
                _bt.start()
                result = self._post_portal_instant_hunt(
                    death_event=_death_event, stop_event=_stop_event,
                    death_thread=_death_thread, respawn_enabled=_respawn_enabled,
                    boss_event=_boss_event,
                )
                if _bt: _bt.join(timeout=2.0)
                if _boss_event.is_set() and not _death_event.is_set() and self._running:
                    if not self._turn_off_auto_hunt(_stop_event):
                        _stop_event.set()
                        if _death_thread: _death_thread.join(timeout=2.0)
                        return False
                    result = self._run_boss_sequence(boss_cfg, _death_event, _stop_event, _death_thread, _respawn_enabled)
                    _stop_event.set()
                    if _death_thread: _death_thread.join(timeout=2.0)
                    return result
                _stop_event.set()
                if _death_thread: _death_thread.join(timeout=2.0)
                return result

        self.log("[커스텀이동] 자동사냥 시작", "success")
        return self._post_portal_instant_hunt(
            death_event=_death_event,
            stop_event=_stop_event,
            death_thread=_death_thread,
            respawn_enabled=_respawn_enabled,
        )

    def _post_portal_instant_hunt(
        self,
        death_event: "threading.Event | None" = None,
        stop_event:  "threading.Event | None" = None,
        death_thread: "threading.Thread | None" = None,
        respawn_enabled: "bool | None" = None,
        boss_event: "threading.Event | None" = None,
        boss_cfg: "dict | None" = None,
    ) -> bool:
        """포탈 진입 후 즉시 해당 맵 자동사냥 진행 (액션 0).
        death_event/stop_event 가 전달되면 기존 스레드를 재사용 (액션 1에서 호출 시).
        boss_cfg가 있으면 보스 로직도 처리 (standalone 호출 시만).
        반환: True=정상완료, False=사망 감지(suicide 재시작 필요)"""
        self.log("[자동사냥] 포탈 진입 후 즉시 자동사냥 시작", "info")

        # ── 외부에서 이벤트가 전달된 경우 재사용, 아니면 새로 생성 ──
        _owns_thread = death_event is None
        _bt = None  # 내부 보스 타이머 스레드
        if _owns_thread:
            _death_event = threading.Event()
            _stop_event  = threading.Event()
            _cfg = load_config()
            _respawn_enabled = _cfg.get(
                "normal_hunt_respawn" if _cfg.get("normal_hunt_enabled") else "boss_raid_respawn",
                True
            )

            def _death_check_loop():
                """병렬 사망 감지: 40번 픽셀 서치 (X:13, Y:49) — RGB=(0,0,0) → 사망"""
                _PIX_X, _PIX_Y = 13, 49
                self.log("[사망감지] 픽셀 감시 시작 (40번 X:13 Y:49)", "info")
                while self._running and not _stop_event.is_set():
                    rgb = _get_pixel_at_client(_PIX_X, _PIX_Y)
                    if rgb is None:
                        time.sleep(1.0)
                        continue
                    pr, pg, pb = rgb
                    _is_black   = (pr == 0 and pg == 0 and pb == 0)
                    _brightness = max(pr, pg, pb) / 255.0
                    _bar        = "█" * int(_brightness * 10) + "░" * (10 - int(_brightness * 10))
                    # 살아있음 → 상태바에만 표시 (로그 패널 덮어쓰기 방지)
                    self.status(f"사망감지 ({pr},{pg},{pb}) [{_bar}]",
                                RED if _is_black else GREEN)
                    if _is_black:
                        self.log(
                            f"[사망감지] 40번 픽셀 ({pr:3d},{pg:3d},{pb:3d}) [{_bar}] → 사망!",
                            "warn"
                        )
                        self.log("[사망감지] 영웅 사망 확정 → suicide 루프 재시작", "warn")
                        self.status("영웅 사망 감지!", RED)
                        _death_event.set()
                        return
                    time.sleep(1.0)

            # 사냥터 복귀 체크박스가 ON일 때만 사망 감지 스레드 시작
            if _respawn_enabled:
                _death_thread = threading.Thread(target=_death_check_loop, daemon=True)
                _death_thread.start()
            else:
                _death_thread = None

            # ── standalone 호출 시 boss_cfg 처리 ──
            if boss_cfg and boss_cfg["use_boss"]:
                if not boss_cfg["boss_timer_on"]:
                    # 타이머 없음 → 즉시 보스 이동 + 전투 (자동사냥 스킵)
                    self.log("[자동사냥] 보스 설정 감지 → 보스 이동 시작", "info")
                    result = self._run_boss_sequence(boss_cfg, _death_event, _stop_event, _death_thread, _respawn_enabled)
                    _stop_event.set()
                    if _death_thread: _death_thread.join(timeout=2.0)
                    return result
                else:
                    # 타이머 있음 → 자동사냥 후 타이머 만료 시 보스
                    _boss_timer_sec = boss_cfg["boss_timer_sec"]
                    _be = threading.Event()
                    def _boss_timer_fn(_be=_be):
                        self.log(f"[보스 타이머] {_boss_timer_sec:.3f}초 후 보스 이동 예정", "info")
                        _dl = time.time() + _boss_timer_sec
                        while time.time() < _dl:
                            if not self._running or _death_event.is_set() or _stop_event.is_set(): return
                            time.sleep(0.25)
                        if self._running and not _death_event.is_set() and not _stop_event.is_set():
                            self.log("[보스 타이머] 타이머 만료 → 자동사냥 해제 후 보스 이동", "warn")
                            _be.set()
                    _bt = threading.Thread(target=_boss_timer_fn, daemon=True)
                    _bt.start()
            else:
                _be = boss_event  # None (no boss) or inherited boss_event
        else:
            _death_event     = death_event
            _stop_event      = stop_event
            _death_thread    = death_thread
            _respawn_enabled = respawn_enabled
            _be = boss_event  # 보스 타이머 이벤트 (없으면 None)

        def _boss_or_death():
            return _death_event.is_set() or (_be is not None and _be.is_set())

        # ── Phase 1: 자동사냥 ON 설정 루프 ──
        while self._running and not _boss_or_death():
            # Step 1: 13번 감지 후 클릭
            while self._running and not _boss_or_death():
                ok13, coords13 = self._wait_for_image(IMG.LOADING_CURSOR,
                                                       timeout=2.0, click=False)
                if not ok13:
                    continue
                if coords13:
                    click_image_center(coords13[0], coords13[1])
                    self.log("[자동사냥] 13번 클릭 완료", "info")
                break

            if not self._running or _boss_or_death():
                break

            # Step 2: 37번 검증
            ok37, _ = self._wait_for_image(IMG.HUNT_ON_CHECK,
                                           timeout=2.0, click=False)
            if ok37:
                self.log("[자동사냥] 자동사냥 ON 확인 완료", "success")
                self.status("자동사냥 진행 중", GREEN)
                break
            self.log("[자동사냥] 자동사냥ON 검증 실패 → 13번부터 재시도", "warn")

        # ── Phase 2: 자동사냥 중 감시 (사망 또는 보스 타이머 만료까지 대기) ──
        if self._running and not _boss_or_death():
            self.log("[자동사냥] 사냥 중 감시 시작", "info")
            while self._running and not _boss_or_death():
                time.sleep(0.25)

        # 보스 타이머 만료로 루프 탈출
        if _be is not None and _be.is_set() and not _death_event.is_set():
            if _owns_thread and boss_cfg and boss_cfg["use_boss"]:
                # standalone 호출 → 자동사냥 OFF 후 보스 이동
                if _bt: _bt.join(timeout=2.0)
                if not self._turn_off_auto_hunt(_stop_event):
                    _stop_event.set()
                    if _death_thread: _death_thread.join(timeout=2.0)
                    return False
                result = self._run_boss_sequence(boss_cfg, _death_event, _stop_event, _death_thread, _respawn_enabled)
                _stop_event.set()
                if _death_thread: _death_thread.join(timeout=2.0)
                return result
            return True  # caller에서 보스 이동 처리 (zone_hunt 등)

        # 사망 감지 스레드 종료 (owns_thread일 때만)
        if _owns_thread:
            _stop_event.set()
            if _death_thread:
                _death_thread.join(timeout=2.0)

        if _death_event.is_set():
            return False  # 사망 → suicide 루프 재시작
        return True  # 정상 완료

    # ── 포탈 활성 여부 확인 ──────────────────────────
    @staticmethod
    def _portal_active() -> bool:
        """일반 사냥터 또는 보스 레이드가 활성화되고 포탈 키가 지정됐는지 확인."""
        cfg = load_config()
        if cfg.get("normal_hunt_enabled", False):
            if cfg.get("normal_hunt_portal_key", ""):
                return True
        if cfg.get("boss_raid_enabled", False):
            if cfg.get("boss_raid_portal_key", ""):
                return True
        return False

    # ── 스타트 스피드 0 설정 (OpenCirnix GameDll.StartDelay 포팅) ──
    def _set_start_speed_zero(self) -> bool:
        ok, msg = write_start_speed_zero()
        if ok:
            self.log(msg, "success")
        else:
            self.log(msg, "warn" if "[경고]" in msg else "error")
        return ok

    # ── 딜레이 메모리 직접 쓰기 (OpenCirnix ControlDelay 포팅) ──
    def _set_game_delay(self, delay: int) -> bool:
        ok, msg = write_game_delay(delay)
        if ok:
            self.log(msg, "success")
        else:
            self.log(msg, "warn" if "[경고]" in msg else "error")
        return ok

    # ── 플레이어 수 읽기 (OpenCirnix 포팅) ──────────
    _OSTCP_PATTERN = bytes([0x4C, 0x7F, 0x65, 0x07, 0x4C])

    def _read_player_count(self) -> "int | None":
        """storm.dll+0x58160 → 포인터 체인 → +0x340 = 현재 방 인원 수"""
        try:
            pm = pymem.Pymem("War3.exe")
            storm_base = None
            for mod in pymem.process.enum_process_module(pm.process_handle):
                if os.path.basename(mod.name).lower() == "storm.dll":
                    storm_base = int(mod.lpBaseOfDll)
                    break
            if storm_base is None:
                pm.close_process(); return None
            ptr = pm.read_uint(storm_base + 0x58160)
            if ptr == 0:
                pm.close_process(); return None
            pat_len = len(self._OSTCP_PATTERN)
            for _ in range(2000):
                try:
                    data = pm.read_bytes(ptr, 4 + pat_len)
                except Exception:
                    pm.close_process(); return None
                if data[4:4 + pat_len] == self._OSTCP_PATTERN:
                    count = pm.read_int(ptr + 0x340)
                    pm.close_process(); return count
                next_ptr = int.from_bytes(data[:4], "little")
                if next_ptr == 0: break
                ptr = next_ptr
            pm.close_process(); return None
        except Exception:
            return None

    def _run_auto_start(self, required_count: int):
        """인원수 충족 시 10초 카운트다운 → Alt+S (게임 강제 시작).
        auto_start_timeout 초 경과 시 인원 미달이어도 강제 시작 (0 = 무제한)."""
        cfg = load_config()
        wait_timeout = cfg.get("auto_start_timeout", 180)  # 0 = 무제한
        timeout_msg = f", 타임아웃: {wait_timeout}초" if wait_timeout > 0 else ""
        self.log(f"자동 시작 대기 중... (목표 인원: {required_count}명{timeout_msg})", "info")
        self.status(f"자동 시작 대기 ({required_count}명)...", YELLOW)

        deadline = (time.time() + wait_timeout) if wait_timeout > 0 else None
        timed_out = False
        first = True
        while self._running:
            if deadline and time.time() >= deadline:
                cur = self._read_player_count() or 0
                self.log(f"[타임아웃] {wait_timeout}초 경과 → 인원 무시하고 시작 ({cur}/{required_count}명)", "warn")
                self.status("타임아웃 → 강제 시작", YELLOW)
                timed_out = True
                break
            count = self._read_player_count()
            if count is not None:
                remaining_s = f"  ({max(0, deadline - time.time()):.0f}s 남음)" if deadline else ""
                msg = f"[{now()}] 현재 인원: {count}/{required_count}명{remaining_s}"
                if first:
                    self.log_signal.emit(msg, "info"); first = False
                if count >= required_count:
                    break
            time.sleep(0.5)

        if not self._running: return

        # ── 타임아웃 경로: 12번 이미지 더블클릭 ──
        if timed_out:
            self.log("12.인원수타임아웃강제시작.png 서치 후 더블클릭", "info")
            ok12, _, coords12, _ = _image_match(IMG.LOADING_TIMEOUT)
            if ok12 and coords12:
                click_image_center(coords12[0], coords12[1])
                time.sleep(0.5)
                click_image_center(coords12[0], coords12[1])
                self.log("12번 더블클릭 완료 → 강제 시작", "success")
                self.status("강제 시작!", GREEN)
            else:
                self.log("[경고] 12번 이미지 감지 실패", "warn")
            return

        # ── 정상 경로: 10초 카운트다운 → Alt+S ──
        count_now = self._read_player_count() or required_count
        self.log(f"인원 충족! ({count_now}명) 10초 후 게임을 시작합니다.", "success")

        # ── 카운트다운 채팅 (WriteProcessMemory, WC3 색상코드 포함) ──
        # |cFFFF0000 = 리얼레드(n초), |cFFFFD700 = 골드(나머지), |r = 리셋
        _chat_hwnd = find_war3_hwnd()
        _initial_msg = "|cFFFF000010초|r|cFFFFD700 후 게임이 시작됩니다|r"
        ok, _msg = send_chat_memory(_chat_hwnd, _initial_msg) if _chat_hwnd else (False, "hwnd 없음")
        if not ok:
            self.log(f"[채팅] {_msg}", "warn")

        for sec in range(10, 0, -1):
            if not self._running: return
            cur = self._read_player_count()
            if cur is not None and cur < required_count:
                self.log(f"[!as] 인원 부족 ({cur}/{required_count}명) → 자동 시작 취소", "warn")
                self.status("자동 시작 취소됨", RED)
                return
            self.log(f"[!as] {sec}초 후 게임 시작...")
            self.status(f"!as 카운트다운: {sec}초", YELLOW)
            if sec < 10:  # 10초는 이미 위에서 전송
                _chat_hwnd = find_war3_hwnd()
                if _chat_hwnd:
                    _cnt_msg = f"|cFFFF0000{sec}초|r|cFFFFD700 남았습니다|r"
                    send_chat_memory(_chat_hwnd, _cnt_msg)
            if not self._sleep(1.0): return

        if not self._running: return

        hwnd = find_war3_hwnd()
        if hwnd:
            win32api.PostMessage(hwnd, 0x100, 0x12, 0)  # WM_KEYDOWN VK_MENU (Alt)
            win32api.PostMessage(hwnd, 0x100, 0x53, 0)  # WM_KEYDOWN 'S'
            win32api.PostMessage(hwnd, 0x101, 0x12, 0)  # WM_KEYUP   VK_MENU
            win32api.PostMessage(hwnd, 0x101, 0x53, 0)  # WM_KEYUP   'S'
            self.log("게임 시작! (Alt+S)", "success")
            self.status("게임 시작!", GREEN)
        else:
            self.log("[경고] War3 창을 찾지 못했습니다.", "warn")

    def _host_loop(self):
        """방장 전용: 7번 클릭 → 방 만들기 진입 → 설정 → Ctrl+V+Tab+C."""
        self.log("=== 방장 매크로 시작 ===", "info")
        coords7 = None

        while self._running:
            # ── 7번 클릭 ──
            self.log("7.방목록입장.png 클릭 중...", "info")
            self.status("방 만들기 진입 중...", YELLOW)
            ok7, coords7 = self._wait_for_image(IMG.ROOM_LIST, timeout=15, click=True)
            if not ok7:
                self.log("[경고] 7번 감지 실패 → Tab+G 후 재시도", "warn")
                _press_vk(_VK_TAB); time.sleep(0.02)
                _press_vk(_VK_TAB, keyup=True); time.sleep(0.3)
                _press_vk(_VK_G); time.sleep(0.02)
                _press_vk(_VK_G, keyup=True); time.sleep(0.3)
                continue

            # ── 9번 → 방만들기 → 8번 감지 (6번 오류시 9번부터 재시도) ──
            room_joined = False
            while self._running:
                # 9번 서치 (10초, 미감지시 7번 재클릭)
                coords9 = None
                while self._running:
                    ok9, coords9 = self._wait_for_image(
                        IMG.ROOM_CREATE, timeout=10, click=False)
                    if ok9:
                        break
                    self.log("9번 미감지 (10s) → 7번 재클릭", "warn")
                    if coords7:
                        click_image_center(coords7[0], coords7[1])

                if not self._running:
                    break

                # ── 공개/비공개 라디오버튼 클릭 (9번 감지 좌표 + 오프셋) ──
                cfg = load_config()
                is_private = cfg.get("room_private", False)
                if is_private:
                    if coords9:
                        ox, oy = -80, 30
                        self.log(f"비공개방 라디오버튼 클릭 (오프셋 {ox},{oy})", "info")
                        click_image_center(coords9[0] + ox, coords9[1] + oy)
                        if not self._sleep(0.2): return
                    else:
                        self.log("[경고] 9번 좌표 없음 → 라디오버튼 클릭 건너뜀", "warn")
                else:
                    self.log("공개방 디폴트값 → 라디오버튼 클릭 생략", "info")

                # ── Ctrl+V → Tab → C → Enter (방 만들기 확정) ──
                hwnd = find_war3_hwnd()
                if hwnd:
                    _user32.SetForegroundWindow(hwnd)
                    if not self._sleep(0.1): return
                _press_vk(_VK_CONTROL)
                _press_vk(_VK_V); time.sleep(0.02)
                _press_vk(_VK_V, keyup=True)
                _press_vk(_VK_CONTROL, keyup=True)
                time.sleep(0.3)
                _press_vk(_VK_TAB); time.sleep(0.02)
                _press_vk(_VK_TAB, keyup=True); time.sleep(0.3)
                _press_vk(_VK_C); time.sleep(0.02)
                _press_vk(_VK_C, keyup=True); time.sleep(0.3)
                _press_vk(_VK_RETURN); time.sleep(0.02)
                _press_vk(_VK_RETURN, keyup=True)
                self.log("방 만들기 완료! (Ctrl+V + Tab + C + Enter)", "success")
                self.status("방 진입 대기 중...", YELLOW)

                # ── 8번/6번 동시 감지 루프 (10초 타임아웃 → 9번부터 재시도) ──
                deadline8 = time.time() + 10
                first8 = True
                while self._running and time.time() < deadline8:
                    ok8_now, val8, _, _ = _image_match(IMG.ROOM_ENTER)
                    remaining8 = max(0.0, deadline8 - time.time())
                    if val8 >= 0:
                        bar8 = "█" * int(val8 * 10) + "░" * (10 - int(val8 * 10))
                        if ok8_now:
                            msg8 = f"[서치] 8.방입장체크(동맹).png → 감지! [{bar8}] {val8:.3f}"
                            self.log_signal.emit(f"[{now()}] {msg8}", "success")
                            room_joined = True
                            break
                        else:
                            msg8 = f"[서치] 8.방입장체크(동맹).png → 미감지  [{bar8}] {val8:.3f}  ({remaining8:.1f}s 남음)"
                    else:
                        msg8 = f"[서치] 8.방입장체크(동맹).png → WC3 창 없음  ({remaining8:.1f}s 남음)"
                    if first8:
                        self.log_signal.emit(f"[{now()}] {msg8}", "warn")
                        first8 = False
                    ok6, _, coords6, _ = _image_match(IMG.LOGIN_WRONG_PW)
                    if ok6 and coords6:
                        self.log("6번(비번오류) 감지 → 확인 클릭 → 9번부터 재시도", "warn")
                        self.status("비밀번호 오류 복구 중...", RED)
                        click_image_center(coords6[0], coords6[1])
                        break
                    if not self._sleep(0.25): return
                if not room_joined and not self._running:
                    break
                # 8번 미감지(타임아웃) 또는 6번 클릭 후 → 외부 루프 continue → 9번부터

                if room_joined or not self._running:
                    break
                # 6번 감지 후 → continue → 9번부터 재시도

            if not self._running:
                return
            if not room_joined:
                self.log("[경고] 방 진입 감지 실패", "warn")
                self.status("방 진입 실패", RED)
                return

            self.log("방 진입 완료!", "success")
            self.status("방 안정화 중...", YELLOW)

            # 5초 안정화
            for sec in range(5, 0, -1):
                if not self._running: return
                self.log(f"안정화 대기: {sec}초...")
                if not self._sleep(1.0): return

            # ── 딜레이 직접 쓰기 (방장 전용, OpenCirnix ControlDelay 동일 방식) ──
            cfg = load_config()
            dr_val = cfg.get("dr_delay", 15)
            self.log(f"딜레이 리듀스 적용 중: {dr_val}ms", "info")
            self._set_game_delay(dr_val)

            # ── 시작속도 0 설정 (!ss 0 하드코딩) ──
            self.log("시작속도 0 설정 중... (!ss 0)", "info")
            self._set_start_speed_zero()

            # ── 자동 시작 ──
            auto_start = cfg.get("auto_start", False)
            auto_count = cfg.get("auto_start_count", 1)
            if auto_start and auto_count > 0:
                self._run_auto_start(auto_count)

            if not self._running: return

            # ── 로딩 완료 대기 (11번) ──
            result = self._wait_loading()
            if result == "loaded":
                return
            if result == "ejected":
                # 5번 → Tab+G → 7번 클릭부터 (outer while 루프)
                self.log("로딩 중 강퇴/이탈 → 방 다시 만들기", "warn")
                _press_vk(_VK_TAB); time.sleep(0.02)
                _press_vk(_VK_TAB, keyup=True); time.sleep(0.3)
                _press_vk(_VK_G); time.sleep(0.02)
                _press_vk(_VK_G, keyup=True); time.sleep(0.3)
                continue  # outer while → 7번 클릭부터
            return  # "timeout": War3 재실행됨 → 워커 종료

