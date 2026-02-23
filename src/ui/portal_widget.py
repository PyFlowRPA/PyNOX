"""
ui/portal_widget.py — 포탈 구역 선택 위젯 (PortalZoneWidget) + 보스 패널 (PortalBossPanel)
"""
from dataclasses import dataclass, field
from typing import List, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QRadioButton, QCheckBox, QLabel, QLineEdit,
    QButtonGroup,
)

from src.ui.theme import (
    DARK_PANEL, DARK_BORDER, ACCENT, TEXT, TEXT_DIM, YELLOW,
)
from src.utils.config import load_config, save_config


@dataclass
class PortalConfig:
    key: str                             # "q", "w", "e", ...
    name: str                            # "Q 포탈 | 라하린 숲"
    zone_names: List[str]                # 구역 라디오 버튼 이름 목록
    boss_defs: List[Tuple[str, str]]     # [(config_key, display_label), ...]
    cfg_prefix: str                      # "nh", "nh_w", "nh_e", ...


class PortalZoneWidget(QWidget):
    """포탈별 구역 선택 서브패널 (구역 라디오 버튼만; 보스 UI는 PortalBossPanel로 분리)."""

    zone_changed = Signal()   # 구역 라디오 변경 시 emit

    def __init__(self, portal: PortalConfig, parent=None):
        super().__init__(parent)
        self._portal = portal
        self._zone_rbs: "list[QRadioButton]" = []
        self._build_ui()

    # ── 설정 키 헬퍼 ──────────────────────────────────
    def _k(self, suffix: str) -> str:
        return f"{self._portal.cfg_prefix}_{suffix}"

    # ── UI 빌드 ───────────────────────────────────────
    def _build_ui(self):
        p   = self._portal
        cfg = load_config()

        self.setStyleSheet(
            f"QFrame {{ border:1px solid {DARK_BORDER}; border-radius:6px; }}"
            f"QLabel, QRadioButton {{ border:none; background:transparent; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(5)

        saved_idx = cfg.get(self._k("zone_idx"), 0)
        zone_grp  = QButtonGroup(self)
        for i, zname in enumerate(p.zone_names):
            rb = QRadioButton(zname)
            rb.setChecked(i == saved_idx)
            zone_grp.addButton(rb, i)
            lay.addWidget(rb)
            self._zone_rbs.append(rb)
        zone_grp.idClicked.connect(
            lambda i: (
                save_config({**load_config(), self._k("zone_idx"): i}),
                self.zone_changed.emit(),
            )
        )

    def sync_ui(self):
        """호환성 유지용 no-op. 구역 라디오 버튼은 항상 활성 상태."""
        pass


class PortalBossPanel(QWidget):
    """포탈별 보스 설정 패널 (보스 체크박스 + 보스 타이머 + 우선 토벌).
    boss_defs가 비어있는 포탈(X 포탈)은 이 패널을 인스턴스화하지 않는다.
    """

    boss_state_changed = Signal()   # 보스 체크 or 타이머 체크 변경시 emit

    def __init__(self, portal: PortalConfig, parent=None):
        super().__init__(parent)
        self._portal = portal
        self._boss_chks:      "list[tuple[str, QCheckBox]]" = []
        self._boss_labels:    "dict[str, str]"             = {}  # cfg_key → 원본 라벨
        self._boss_rank_lbls: "dict[str, QLabel]"          = {}  # cfg_key → 순위 QLabel
        self._chk_boss_timer:     "QCheckBox | None" = None
        self._led_boss_timer:     "QLineEdit | None" = None
        self._chk_boss_priority:  "QCheckBox | None" = None
        self._chk_boss_no_return: "QCheckBox | None" = None
        self._lbl_timer_sec:      "QLabel | None"    = None
        self._lbl_timer_desc:     "QLabel | None"    = None
        self._lbl_priority_desc:  "QLabel | None"    = None
        self._build_ui()

    # ── 설정 키 헬퍼 ──────────────────────────────────
    def _k(self, suffix: str) -> str:
        return f"{self._portal.cfg_prefix}_{suffix}"

    # ── UI 빌드 ───────────────────────────────────────
    def _build_ui(self):
        p   = self._portal
        cfg = load_config()

        self.setStyleSheet(
            f"QFrame {{ border:1px solid {DARK_BORDER}; border-radius:6px; }}"
            f"QLabel, QCheckBox {{ border:none; background:transparent; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(5)

        # ── 보스 체크박스 ──
        _init_order = list(cfg.get(self._k("boss_order"), []))
        # 최초 로드 시 체크된 보스가 있지만 순서 미설정이면 정의 순서로 초기화
        if not _init_order:
            _checked = [k for k, _ in p.boss_defs if cfg.get(k, False)]
            if _checked:
                _init_order = _checked
                save_config({**cfg, self._k("boss_order"): _init_order})

        for cfg_key, label in p.boss_defs:
            self._boss_labels[cfg_key] = label
            _checked = cfg.get(cfg_key, False)
            _rank    = _init_order.index(cfg_key) if cfg_key in _init_order and _checked else -1

            _row = QHBoxLayout()
            _row.setSpacing(6)   # 보스 타이머 행 spacing과 동일
            _row.setContentsMargins(0, 0, 0, 0)

            chk = QCheckBox("")   # 인디케이터만, 텍스트는 QLabel로 처리
            chk.setChecked(_checked)
            chk.setStyleSheet("QCheckBox { spacing: 0px; }")  # 내부 간격 제거 → 인디케이터 폭만 차지
            _row.addWidget(chk)

            _rlbl = QLabel()
            _rlbl.setTextFormat(Qt.RichText)
            _rlbl.setStyleSheet("border:none; background:transparent;")
            _rlbl.mousePressEvent = lambda _e, c=chk: c.toggle()
            _rlbl.setText(self._rank_html(label, _rank))
            self._boss_rank_lbls[cfg_key] = _rlbl
            _row.addWidget(_rlbl)
            _row.addStretch()
            lay.addLayout(_row)

            self._boss_chks.append((cfg_key, chk))

        # ── 보스 타이머 행 ──
        timer_row = QHBoxLayout()
        timer_row.setSpacing(6)

        self._chk_boss_timer = QCheckBox("보스 타이머(병렬):")
        self._chk_boss_timer.setChecked(cfg.get(self._k("boss_timer"), False))
        self._chk_boss_timer.setStyleSheet(f"color:{YELLOW}; font-weight:bold;")
        timer_row.addWidget(self._chk_boss_timer)

        self._led_boss_timer = QLineEdit(str(cfg.get(self._k("boss_timer_sec"), 60.0)))
        self._led_boss_timer.setFixedWidth(90)
        self._led_boss_timer.setPlaceholderText("초")
        self._led_boss_timer.setStyleSheet(
            f"background:{DARK_PANEL}; border:1px solid {DARK_BORDER};"
            f"border-radius:4px; padding:2px 6px; color:{TEXT};"
        )
        self._led_boss_timer.editingFinished.connect(self._on_timer_sec_edited)
        self._led_boss_timer.textChanged.connect(
            lambda _: self.boss_state_changed.emit()
        )
        timer_row.addWidget(self._led_boss_timer)

        self._lbl_timer_sec = QLabel("초")
        self._lbl_timer_sec.setStyleSheet(f"color:{TEXT_DIM};")
        timer_row.addWidget(self._lbl_timer_sec)
        timer_row.addStretch()
        lay.addLayout(timer_row)

        self._lbl_timer_desc = QLabel("  └─ 활성화시 필드사냥을 하다가 세팅된 타이머에 맞춰 보스 진행")
        self._lbl_timer_desc.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        lay.addWidget(self._lbl_timer_desc)

        # ── 보스 우선 토벌 ──
        self._chk_boss_priority = QCheckBox("매크로 시작시 보스 우선 토벌")
        self._chk_boss_priority.setChecked(cfg.get(self._k("boss_priority"), False))
        self._chk_boss_priority.setStyleSheet(f"color:{YELLOW}; font-weight:bold;")
        self._chk_boss_priority.stateChanged.connect(
            lambda s: (
                save_config({**load_config(), self._k("boss_priority"): bool(s)}),
                self.boss_state_changed.emit(),
            )
        )
        lay.addWidget(self._chk_boss_priority)

        self._lbl_priority_desc = QLabel("  └─ 활성화시 필드를 우선적으로 가지 않고 보스부터 진행 후 필드사냥 진행")
        self._lbl_priority_desc.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        lay.addWidget(self._lbl_priority_desc)

        # ── 보스 처치 후 필드 복귀 (no return) ──
        self._chk_boss_no_return = QCheckBox("보스 처치 후 필드 경유시 마을로 복귀하지 않음")
        self._chk_boss_no_return.setChecked(cfg.get(self._k("boss_no_return"), False))
        self._chk_boss_no_return.setStyleSheet(f"color:{YELLOW}; font-weight:bold;")
        self._chk_boss_no_return.stateChanged.connect(
            lambda s: (
                save_config({**load_config(), self._k("boss_no_return"): bool(s)}),
                self.boss_state_changed.emit(),
            )
        )
        lay.addWidget(self._chk_boss_no_return)

        _lbl_no_return_desc = QLabel("  └─ 활성화시 보스 처치 후 suicide 없이 필드로 직접 복귀 후 사냥 재개")
        _lbl_no_return_desc.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        lay.addWidget(_lbl_no_return_desc)

        # ── 시그널 연결 ──
        for cfg_key, chk in self._boss_chks:
            chk.stateChanged.connect(
                lambda c, k=cfg_key: self._on_boss_chk_changed(k, c)
            )
        self._chk_boss_timer.stateChanged.connect(
            lambda c: (
                save_config({**load_config(), self._k("boss_timer"): bool(c)}),
                self.sync_ui(),
                self.boss_state_changed.emit(),
            )
        )

        self.sync_ui()

    # ── 보스 체크 변경 ────────────────────────────────
    def _on_boss_chk_changed(self, cfg_key: str, state: int):
        """체크 순서 리스트 갱신 → 저장 → 순위 레이블 갱신 → sync_ui → 시그널."""
        checked = bool(state)
        cfg     = load_config()
        order   = list(cfg.get(self._k("boss_order"), []))
        if checked:
            if cfg_key not in order:
                order.append(cfg_key)
        else:
            if cfg_key in order:
                order.remove(cfg_key)
        cfg[cfg_key]                  = checked
        cfg[self._k("boss_order")]    = order
        save_config(cfg)
        self._update_rank_labels(order)
        self.sync_ui()
        self.boss_state_changed.emit()

    @staticmethod
    def _rank_html(label: str, rank: int) -> str:
        """순위 프리픽스 포함 Rich Text 생성. rank < 0 이면 프리픽스 없음."""
        boss_html = f"<span style='color:{YELLOW}; font-weight:bold;'>{label}</span>"
        if rank >= 0:
            prefix = (f"<span style='color:#f38bab; font-weight:bold;'>"
                      f"[{rank + 1}]</span> ")
            return prefix + boss_html
        return boss_html

    def _update_rank_labels(self, order: "list | None" = None):
        """체크 순서에 따라 [1] [2] ... 프리픽스를 QLabel에 반영."""
        if order is None:
            order = load_config().get(self._k("boss_order"), [])
        for cfg_key, chk in self._boss_chks:
            lbl  = self._boss_rank_lbls.get(cfg_key)
            orig = self._boss_labels.get(cfg_key, "")
            if lbl is None:
                continue
            rank = order.index(cfg_key) if (chk.isChecked() and cfg_key in order) else -1
            lbl.setText(self._rank_html(orig, rank))

    # ── 상태 동기화 ──────────────────────────────────
    def sync_ui(self):
        """보스 체크 상태에 따라 타이머/우선토벌 위젯 활성/비활성 제어."""
        if not self._boss_chks:
            return

        any_boss       = any(chk.isChecked() for _, chk in self._boss_chks)
        timer_on       = self._chk_boss_timer.isChecked() if self._chk_boss_timer else False
        timer_field_on = any_boss and timer_on

        # ── 보스 체크박스 ──
        for cfg_key, chk in self._boss_chks:
            chk.setEnabled(True)
            lbl = self._boss_rank_lbls.get(cfg_key)
            if lbl:
                lbl.setEnabled(True)

        # ── 타이머 ──
        if self._chk_boss_timer:
            self._chk_boss_timer.setEnabled(any_boss)
            self._chk_boss_timer.setStyleSheet(
                f"color:{YELLOW}; font-weight:bold;" if any_boss else f"color:{TEXT_DIM};"
            )
        if self._led_boss_timer:
            self._led_boss_timer.setEnabled(timer_field_on)
            self._led_boss_timer.setStyleSheet(
                f"background:{DARK_PANEL}; border:1px solid {ACCENT};"
                f"border-radius:4px; padding:2px 6px; color:{TEXT};"
                if timer_field_on else
                f"background:{DARK_PANEL}; border:1px solid {DARK_BORDER};"
                f"border-radius:4px; padding:2px 6px; color:{TEXT_DIM};"
            )
        if self._lbl_timer_sec:
            self._lbl_timer_sec.setStyleSheet(
                f"color:{TEXT};" if timer_field_on else f"color:{TEXT_DIM};"
            )
        if self._lbl_timer_desc:
            self._lbl_timer_desc.setStyleSheet(
                f"color:{TEXT_DIM}; font-size:11px;" if any_boss
                else f"color:{DARK_BORDER}; font-size:11px;"
            )

        # ── 우선 토벌 / 복귀 안함 ──
        if self._chk_boss_priority:
            self._chk_boss_priority.setEnabled(timer_field_on)
            self._chk_boss_priority.setStyleSheet(
                f"color:{YELLOW}; font-weight:bold;" if timer_field_on else f"color:{TEXT_DIM};"
            )
        if self._lbl_priority_desc:
            self._lbl_priority_desc.setStyleSheet(
                f"color:{TEXT_DIM}; font-size:11px;" if timer_field_on
                else f"color:{DARK_BORDER}; font-size:11px;"
            )
        if self._chk_boss_no_return:
            self._chk_boss_no_return.setEnabled(timer_field_on)
            self._chk_boss_no_return.setStyleSheet(
                f"color:{YELLOW}; font-weight:bold;" if timer_field_on else f"color:{TEXT_DIM};"
            )

    # ── 내부 유틸 ────────────────────────────────────
    @staticmethod
    def _add_sep(layout: QVBoxLayout):
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"border:none; border-top:1px solid {DARK_BORDER};")
        layout.addWidget(sep)

    def _on_timer_sec_edited(self):
        txt = self._led_boss_timer.text()
        try:
            val = float(txt)
        except ValueError:
            val = 60.0
        save_config({**load_config(), self._k("boss_timer_sec"): val})
        self.boss_state_changed.emit()


# ── 포탈 설정 데이터 ──────────────────────────────────────
PORTAL_CONFIGS: "list[PortalConfig]" = [
    PortalConfig(
        key="q",
        name="Q 포탈 | 라하린 숲",
        zone_names=[
            "오래된 숲의 정령 (아래)",
            "오래된 숲의 정령 (위)",
            "동굴 왕 두꺼비",
            "토끼 굴",
            "그을음 도적단 부단장",
        ],
        boss_defs=[
            ("nh_zone_boss",       "[BOSS]  도적단장 - 칼레인"),
            ("nh_q_boss_kingcrab", "[BOSS]  백년 묵은 킹크랩"),
            ("nh_q_boss_giant",    "[BOSS]  늪의 거인"),
            ("nh_q_boss_pap",      "[BOSS]  잊혀진 수호자 - 파프"),
        ],
        cfg_prefix="nh",
    ),
    PortalConfig(
        key="w",
        name="W 포탈 | 아스탈 요새",
        zone_names=[
            "경비대장 로웰",
            "무쇠발톱",
            "TX-005",
            "드워프, 중갑차, 정예병",
        ],
        boss_defs=[("nh_w_zone_boss", "[BOSS]  매직웨건")],
        cfg_prefix="nh_w",
    ),
    PortalConfig(
        key="e",
        name="E 포탈 | 어둠얼음성채",
        zone_names=[
            "바레스",
            "오래된 고대유적 수호자",
            "거울 여왕의 파편",
        ],
        boss_defs=[
            ("nh_e_boss_maureus",  "[BOSS]  마우레우스"),
            ("nh_e_boss_tarod",    "[BOSS]  타로드"),
            ("nh_e_boss_colossus", "[BOSS]  바위거인 콜로서스"),
            ("nh_e_boss_tulak",    "[BOSS]  사도: 툴'락"),
        ],
        cfg_prefix="nh_e",
    ),
    PortalConfig(
        key="r",
        name="R 포탈 | 버려진 고성",
        zone_names=[
            "(LT)제국기사의 망령",
            "(RT)제국기사의 망령",
            "옛 수비대장 펠릭스",
            "옛 집행관 라나",
        ],
        boss_defs=[
            ("nh_r_boss_hedan",    "[BOSS]  보급장교 헤단"),
            ("nh_r_boss_thanatos", "[BOSS]  사신 - 타나토스"),
        ],
        cfg_prefix="nh_r",
    ),
    PortalConfig(
        key="a",
        name="A 포탈 | 바위협곡",
        zone_names=[
            "(7시) 고블린",
            "(5시) 고블린",
            "(10시) 고블린",
            "(2시) 고블린",
            "깊은 동굴 - 거대한 숲 거인",
        ],
        boss_defs=[
            ("nh_a_boss_bx485", "[BOSS]  BX-485"),
            ("nh_a_boss_ivan",  "[BOSS]  엔지니어 - 이반"),
        ],
        cfg_prefix="nh_a",
    ),
    PortalConfig(
        key="s",
        name="S 포탈 | 바람의 협곡",
        zone_names=[
            "(LT) 바람의 정령",
            "(RT) 바람의 정령",
            "중급 바람의 정령 윈디",
            "검은가죽 드루이드",
            "동굴 깊은 곳",
            "상급 바람의 정령 실프",
        ],
        boss_defs=[
            ("nh_s_boss_callis", "[BOSS]  집행자 캘리스"),
            ("nh_s_boss_kalipa", "[BOSS]  마룡: 칼리파"),
        ],
        cfg_prefix="nh_s",
    ),
    PortalConfig(
        key="d",
        name="D 포탈 | 시계태엽 공장",
        zone_names=[
            "(LT) 마정석 골렘",
            "(RT) 마정석 골렘",
        ],
        boss_defs=[
            ("nh_d_boss_klak",   "[BOSS]  클락"),
            ("nh_d_boss_mirdon", "[BOSS]  미르돈"),
            ("nh_d_boss_rex",    "[BOSS]  렉스"),
        ],
        cfg_prefix="nh_d",
    ),
    PortalConfig(
        key="f",
        name="F 포탈 | 속삭임의 숲",
        zone_names=[
            "(위) 강철집게",
            "(아래) 강철집게",
        ],
        boss_defs=[("nh_f_boss_doombaou", "[BOSS]  둠바우")],
        cfg_prefix="nh_f",
    ),
    PortalConfig(
        key="z",
        name="Z 포탈 | 이그니스영역",
        zone_names=[
            "(입구) 용암굴",
            "(위) 용암굴",
            "(LT) 용암굴",
            "(아래) 용암굴",
        ],
        boss_defs=[("nh_z_boss_flame", "[BOSS]  플레임")],
        cfg_prefix="nh_z",
    ),
    PortalConfig(
        key="x",
        name="X 포탈 | 정령계",
        zone_names=[
            "(LT) 정령계",
            "(RT) 정령계",
        ],
        boss_defs=[],   # 보스 없음
        cfg_prefix="nh_x",
    ),
]
