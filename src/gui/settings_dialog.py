# src/gui/settings_dialog.py
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDoubleSpinBox, QPushButton, QLineEdit, QFormLayout, QSpinBox, QCheckBox
from PySide6.QtCore import Qt

class SettingsDialog(QDialog):
    """
    简易设置对话框：会读取 SettingsManager 并写回。
    只包含常见字段：scale, idle interval, screen_watch_enabled, display_name, llm api key, max tokens
    """
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.sm = settings_manager
        self.setWindowTitle("桌宠设置")
        self.setWindowModality(Qt.ApplicationModal)
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout()
        form = QFormLayout()

        # scale
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.2, 3.0)
        self.scale_spin.setSingleStep(0.05)
        form.addRow("显示缩放 (scale)", self.scale_spin)

        # idle interval
        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(1, 3600)
        form.addRow("空闲触发间隔 (秒)", self.idle_spin)

        # screen watch
        self.screen_watch_cb = QCheckBox("启用屏幕监视")
        form.addRow(self.screen_watch_cb)

        # screen watch interval
        self.screen_watch_interval = QSpinBox()
        self.screen_watch_interval.setRange(5, 3600)
        form.addRow("屏幕监视间隔 (秒)", self.screen_watch_interval)

        # display name
        self.user_name = QLineEdit()
        form.addRow("桌宠称呼用户为", self.user_name)

        # LLM API key
        self.llm_key = QLineEdit()
        self.llm_key.setEchoMode(QLineEdit.Password)
        form.addRow("LLM API Key", self.llm_key)

        # max tokens
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(16, 4096)
        form.addRow("LLM max tokens", self.max_tokens)

        layout.addLayout(form)

        # buttons
        btn_save = QPushButton("保存")
        btn_cancel = QPushButton("取消")
        btn_save.clicked.connect(self._on_save)
        btn_cancel.clicked.connect(self.reject)

        btn_layout = QVBoxLayout()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _load_values(self):
        self.scale_spin.setValue(self.sm.get("pet", "scale", default=1.0))
        self.idle_spin.setValue(self.sm.get("behavior", "idle_interval_s", default=7))
        self.screen_watch_cb.setChecked(self.sm.get("behavior", "screen_watch_enabled", default=False))
        self.screen_watch_interval.setValue(self.sm.get("behavior", "screen_watch_interval_s", default=60))
        self.user_name.setText(self.sm.get("user", "display_name", default="主人") or "")
        self.llm_key.setText(self.sm.get("llm", "api_key", default="") or "")
        self.max_tokens.setValue(self.sm.get("llm", "max_tokens", default=512))

    def _on_save(self):
        # write back to settings manager
        self.sm.set("pet", "scale", value=float(self.scale_spin.value()))
        self.sm.set("behavior", "idle_interval_s", value=int(self.idle_spin.value()))
        self.sm.set("behavior", "screen_watch_enabled", value=bool(self.screen_watch_cb.isChecked()))
        self.sm.set("behavior", "screen_watch_interval_s", value=int(self.screen_watch_interval.value()))
        self.sm.set("user", "display_name", value=self.user_name.text().strip())
        self.sm.set("llm", "api_key", value=self.llm_key.text().strip())
        self.sm.set("llm", "max_tokens", value=int(self.max_tokens.value()))
        self.accept()
