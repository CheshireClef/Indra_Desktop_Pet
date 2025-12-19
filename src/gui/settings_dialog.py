from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QCheckBox,
    QPushButton, QLineEdit, QGroupBox, QComboBox
)
from PySide6.QtCore import Qt


class SettingsDialog(QDialog):
    """
    桌宠设置对话框
    """
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.sm = settings_manager

        self.setWindowTitle("桌宠设置")
        self.setWindowModality(Qt.ApplicationModal)

        self._build_ui()
        self._load_values()

    # ---------- UI ----------
    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        # ===== 基础设置 =====
        form = QFormLayout()

        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.2, 3.0)
        self.scale_spin.setSingleStep(0.05)
        form.addRow("显示缩放 (scale)", self.scale_spin)

        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(1, 3600)
        form.addRow("空闲触发间隔 (秒)", self.idle_spin)

        self.screen_watch_cb = QCheckBox("启用屏幕监视")
        form.addRow(self.screen_watch_cb)

        self.screen_watch_interval = QSpinBox()
        self.screen_watch_interval.setRange(5, 3600)
        form.addRow("屏幕监视间隔 (秒)", self.screen_watch_interval)

        self.user_name = QLineEdit()
        form.addRow("桌宠称呼用户为", self.user_name)

        main_layout.addLayout(form)

        # ===== LLM 设置 =====
        main_layout.addWidget(self._build_llm_group())

        # ===== 按钮 =====
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_cancel = QPushButton("取消")

        btn_save.clicked.connect(self._on_save)
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        main_layout.addLayout(btn_layout)

    def _build_llm_group(self):
        group = QGroupBox("语言模型（LLM）")
        layout = QFormLayout(group)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["deepseek", "openai", "custom"])
        layout.addRow("模型提供方", self.provider_combo)

        self.llm_key = QLineEdit()
        self.llm_key.setEchoMode(QLineEdit.Password)
        layout.addRow("API Key", self.llm_key)

        self.base_url_edit = QLineEdit()
        layout.addRow("Base URL", self.base_url_edit)

        self.model_edit = QLineEdit()
        layout.addRow("模型名", self.model_edit)

        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(16, 8192)
        layout.addRow("Max Tokens", self.max_tokens)

        self.history_spin = QSpinBox()
        self.history_spin.setRange(1, 20)
        layout.addRow("保留对话轮数", self.history_spin)

        self.provider_combo.currentTextChanged.connect(
            self._on_provider_changed
        )

        return group

    # ---------- Load ----------
    def _load_values(self):
        self.scale_spin.setValue(self.sm.get("pet", "scale", default=1.0))
        self.idle_spin.setValue(self.sm.get("behavior", "idle_interval_s", default=7))
        self.screen_watch_cb.setChecked(
            self.sm.get("behavior", "screen_watch_enabled", default=False)
        )
        self.screen_watch_interval.setValue(
            self.sm.get("behavior", "screen_watch_interval_s", default=60)
        )
        self.user_name.setText(
            self.sm.get("user", "display_name", default="主人") or ""
        )

        self.provider_combo.setCurrentText(
            self.sm.get("llm", "provider", default="deepseek")
        )
        self.llm_key.setText(self.sm.get("llm", "api_key", default="") or "")
        self.base_url_edit.setText(self.sm.get("llm", "base_url", default="") or "")
        self.model_edit.setText(self.sm.get("llm", "model", default="") or "")
        self.max_tokens.setValue(self.sm.get("llm", "max_tokens", default=512))
        self.history_spin.setValue(self.sm.get("llm", "history_rounds", default=6))

    # ---------- Save ----------
    def _on_save(self):
        self.sm.set("pet", "scale", value=float(self.scale_spin.value()))
        self.sm.set("behavior", "idle_interval_s", value=int(self.idle_spin.value()))
        self.sm.set("behavior", "screen_watch_enabled", value=self.screen_watch_cb.isChecked())
        self.sm.set(
            "behavior",
            "screen_watch_interval_s",
            value=int(self.screen_watch_interval.value())
        )
        self.sm.set("user", "display_name", value=self.user_name.text().strip())

        self.sm.set("llm", "provider", value=self.provider_combo.currentText())
        self.sm.set("llm", "api_key", value=self.llm_key.text().strip())
        self.sm.set("llm", "base_url", value=self.base_url_edit.text().strip())
        self.sm.set("llm", "model", value=self.model_edit.text().strip())
        self.sm.set("llm", "max_tokens", value=int(self.max_tokens.value()))
        self.sm.set("llm", "history_rounds", value=int(self.history_spin.value()))

        self.accept()

    # ---------- Provider change ----------
    def _on_provider_changed(self, provider: str):
        if provider == "deepseek":
            self.base_url_edit.setText("https://api.deepseek.com")
            self.model_edit.setText("deepseek-chat")
        elif provider == "openai":
            self.base_url_edit.setText("https://api.openai.com")
            self.model_edit.setText("gpt-4o-mini")
