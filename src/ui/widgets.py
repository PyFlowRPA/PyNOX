"""
ui/widgets.py — 설정 파일 자동 연동 공용 위젯
"""
from PySide6.QtWidgets import QCheckBox, QSpinBox

from src.utils.config import load_config, update_config


class ConfigSpinBox(QSpinBox):
    """설정 파일과 자동 연동되는 QSpinBox.

    생성 시 cfg_key에서 저장된 값을 불러오고,
    값이 바뀌면 자동으로 update_config(cfg_key, value) 를 호출한다.
    추가 동작이 필요한 경우 valueChanged / editingFinished 를 별도로 연결한다.

    Parameters
    ----------
    cfg_key : str
        wc3_config.json 설정 키
    min_val, max_val : int
        setRange 범위
    default : int
        cfg_key 가 없을 때 사용할 기본값
    suffix : str
        표시 단위 (예: "초", "명", "ms")
    width : int
        setFixedWidth 픽셀 (기본 72)
    step : int
        setSingleStep 값 (기본 1)
    """

    def __init__(self, cfg_key: str, min_val: int, max_val: int,
                 default: int, *, suffix: str = "", width: int = 72,
                 step: int = 1, parent=None):
        super().__init__(parent)
        self._cfg_key = cfg_key
        self.setRange(min_val, max_val)
        self.setSingleStep(step)
        if suffix:
            self.setSuffix(suffix)
        self.setFixedWidth(width)
        self.valueChanged.connect(lambda v: update_config(cfg_key, v))
        self.setValue(load_config().get(cfg_key, default))


class ConfigCheckBox(QCheckBox):
    """설정 파일과 자동 연동되는 QCheckBox.

    생성 시 cfg_key에서 저장된 값을 불러오고,
    토글되면 자동으로 update_config(cfg_key, checked) 를 호출한다.
    추가 동작이 필요한 경우 toggled / stateChanged 를 별도로 연결한다.

    Parameters
    ----------
    cfg_key : str
        wc3_config.json 설정 키
    label : str
        체크박스 텍스트
    default : bool
        cfg_key 가 없을 때 사용할 기본값
    """

    def __init__(self, cfg_key: str, label: str = "", default: bool = False,
                 *, parent=None):
        super().__init__(label, parent)
        self._cfg_key = cfg_key
        self.toggled.connect(lambda v: update_config(cfg_key, v))
        self.setChecked(load_config().get(cfg_key, default))
