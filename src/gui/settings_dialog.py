from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QCheckBox,
    QPushButton, QLineEdit, QGroupBox, QComboBox,
    QTabWidget, QWidget, QSizePolicy  # ✅ 新增导入 QSizePolicy
)
from PySide6.QtCore import Qt


class SettingsDialog(QDialog):
    """
    桌宠设置对话框（标签页版，支持手动调整大小）
    """
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.sm = settings_manager

        self.setWindowTitle("桌宠设置")
        self.setWindowModality(Qt.ApplicationModal)
        
        # ========== 核心修改：启用窗口大小调整 ==========
        self.resize(500, 400)  # 设置初始大小
        self.setSizeGripEnabled(True)  # 右下角显示大小调整手柄
        
        self._build_ui()
        self._load_values()

    # ---------- UI 构建（核心修改：修复 QSizePolicy 调用） ----------
    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        # 1. 创建标签页控件
        self.tab_widget = QTabWidget()
        
        # ✅ 修复：正确设置大小策略（使用 QSizePolicy.Expanding 类属性）
        self.tab_widget.setSizePolicy(
            QSizePolicy.Expanding,  # 水平方向自适应
            QSizePolicy.Expanding   # 垂直方向自适应
        )
        
        # 1.1 第一个标签：基础设置
        self.basic_tab = QWidget()
        self._build_basic_tab()
        self.tab_widget.addTab(self.basic_tab, "基础设置")

        # 1.2 第二个标签：模型设置（LLM + 视觉模型）
        self.model_tab = QWidget()
        self._build_model_tab()
        self.tab_widget.addTab(self.model_tab, "模型设置")

        # 将标签页添加到主布局
        main_layout.addWidget(self.tab_widget)

        # 2. 底部按钮区（保持不变）
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_cancel = QPushButton("取消")

        btn_save.clicked.connect(self._on_save)
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        main_layout.addLayout(btn_layout)

    # ---------- 构建基础设置标签页 ----------
    def _build_basic_tab(self):
        layout = QVBoxLayout(self.basic_tab)
        form = QFormLayout()

        # 基础设置项
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.2, 3.0)
        self.scale_spin.setSingleStep(0.05)
        form.addRow("显示缩放 (scale)", self.scale_spin)

        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(1, 10800)
        form.addRow("空闲后主动行为触发间隔 (秒)", self.idle_spin)

        self.screen_watch_cb = QCheckBox("启用屏幕监视")
        form.addRow(self.screen_watch_cb)

        self.screen_watch_interval = QSpinBox()
        self.screen_watch_interval.setRange(5, 10800)
        form.addRow("屏幕监视间隔 (秒)", self.screen_watch_interval)

        # 临时气泡时长配置
        self.temp_bubble_duration = QSpinBox()
        self.temp_bubble_duration.setRange(1, 60)
        form.addRow("临时聊天气泡显示时长 (秒)", self.temp_bubble_duration)

        self.user_name = QLineEdit()
        form.addRow("桌宠称呼用户为", self.user_name)

        layout.addLayout(form)
        layout.addStretch()

    # ---------- 构建模型设置标签页（LLM + 视觉模型） ----------
    def _build_model_tab(self):
        layout = QVBoxLayout(self.model_tab)

        # LLM 设置组
        llm_group = self._build_llm_group()
        layout.addWidget(llm_group)

        # 视觉模型设置组
        vision_group = self._build_vision_group()
        layout.addWidget(vision_group)

        layout.addStretch()

    # ---------- LLM 组构建方法 ----------
    def _build_llm_group(self):
        group = QGroupBox("对话语言模型（LLM）")
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
        self.history_spin.setRange(1, 100)
        layout.addRow("保留对话轮数", self.history_spin)

        # Temperature 控制
        self.temperature_spinbox = QDoubleSpinBox(self)
        self.temperature_spinbox.setRange(0.0, 1.5)
        self.temperature_spinbox.setSingleStep(0.1)
        self.temperature_spinbox.setValue(self.sm.get("llm", "temperature", default=1.0))
        layout.addRow("对话Temperature参数", self.temperature_spinbox)

        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)

        return group
    
    # ---------- 视觉模型组构建方法 ----------
    def _build_vision_group(self):
        group = QGroupBox("视觉模型（用于解析屏幕截图）")
        layout = QFormLayout(group)

        self.vision_api_url = QLineEdit(self)
        self.vision_api_url.setText(self.sm.get("vision", "api_url", default=""))
        layout.addRow("视觉模型 API URL", self.vision_api_url)

        self.vision_api_key = QLineEdit(self)
        self.vision_api_key.setText(self.sm.get("vision", "api_key", default=""))
        layout.addRow("视觉模型 API Key", self.vision_api_key)

        self.vision_model = QLineEdit(self)
        self.vision_model.setText(self.sm.get("vision", "model", default="Qwen/Qwen3-VL-32B-Instruct"))
        layout.addRow("视觉模型名称", self.vision_model)
        
        return group

    # ---------- 加载配置 ----------
    def _load_values(self):
        # 加载基础设置
        self.scale_spin.setValue(self.sm.get("pet", "scale", default=1.0))
        self.idle_spin.setValue(self.sm.get("behavior", "idle_interval_s", default=7))
        self.screen_watch_cb.setChecked(
            self.sm.get("behavior", "screen_watch_enabled", default=False)
        )
        self.screen_watch_interval.setValue(
            self.sm.get("behavior", "screen_watch_interval_s", default=60)
        )
        self.temp_bubble_duration.setValue(
            self.sm.get("behavior", "temp_bubble_duration_s", default=10)
        )
        self.user_name.setText(
            self.sm.get("user", "display_name", default="主人") or ""
        )

        # 加载LLM设置
        self.provider_combo.setCurrentText(
            self.sm.get("llm", "provider", default="deepseek")
        )
        self.llm_key.setText(self.sm.get("llm", "api_key", default="") or "")
        self.base_url_edit.setText(self.sm.get("llm", "base_url", default="") or "")
        self.model_edit.setText(self.sm.get("llm", "model", default="") or "")
        self.max_tokens.setValue(self.sm.get("llm", "max_tokens", default=512))
        self.history_spin.setValue(self.sm.get("llm", "history_rounds", default=6))
        self.temperature_spinbox.setValue(self.sm.get("llm", "temperature", default=1.0))

        # 加载视觉模型设置
        self.vision_api_url.setText(self.sm.get("vision", "api_url", default=""))
        self.vision_api_key.setText(self.sm.get("vision", "api_key", default=""))
        self.vision_model.setText(self.sm.get("vision", "model", default="Qwen/Qwen3-VL-32B-Instruct"))

    # ---------- 保存配置 ----------
    def _on_save(self):
        # 保存基础设置
        self.sm.set("pet", "scale", value=float(self.scale_spin.value()))
        self.sm.set("behavior", "idle_interval_s", value=int(self.idle_spin.value()))
        self.sm.set("behavior", "screen_watch_enabled", value=self.screen_watch_cb.isChecked())
        self.sm.set(
            "behavior", "screen_watch_interval_s", value=int(self.screen_watch_interval.value())
        )
        self.sm.set(
            "behavior", "temp_bubble_duration_s", value=int(self.temp_bubble_duration.value())
        )
        self.sm.set("user", "display_name", value=self.user_name.text().strip())

        # 保存LLM设置
        self.sm.set("llm", "provider", value=self.provider_combo.currentText())
        self.sm.set("llm", "api_key", value=self.llm_key.text().strip())
        self.sm.set("llm", "base_url", value=self.base_url_edit.text().strip())
        self.sm.set("llm", "model", value=self.model_edit.text().strip())
        self.sm.set("llm", "max_tokens", value=int(self.max_tokens.value()))
        self.sm.set("llm", "history_rounds", value=int(self.history_spin.value()))
        self.sm.set("llm", "temperature", value=self.temperature_spinbox.value())

        # 保存视觉模型设置
        self.sm.set("vision", "api_url", value=self.vision_api_url.text())
        self.sm.set("vision", "api_key", value=self.vision_api_key.text())
        self.sm.set("vision", "model", value=self.vision_model.text())

        self.sm.save()
        self.accept()

    # ---------- 提供方切换 ----------
    def _on_provider_changed(self, provider: str):
        if provider == "deepseek":
            self.base_url_edit.setText("https://api.deepseek.com")
            self.model_edit.setText("deepseek-chat")
        elif provider == "openai":
            self.base_url_edit.setText("https://api.openai.com")
            self.model_edit.setText("gpt-4o-mini")
        elif provider == "custom":
            self.base_url_edit.setText("")
            self.model_edit.setText("")