# src/gui/settings_dialog.py
"""
设置对话框模块
提供用户友好的 GUI 界面来修改 SettingsManager 中的配置。
支持多标签页分类显示 (基础设置 / 模型设置)。
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QCheckBox,
    QPushButton, QLineEdit, QGroupBox, QComboBox,
    QTabWidget, QWidget, QSizePolicy,
    QListWidget, QListWidgetItem, QMessageBox, QAbstractItemView,
    QTextEdit, QDialogButtonBox,
)
from PySide6.QtCore import Qt
from utils import resource_path


class _MemoryContentEditDialog(QDialog):
    """仅编辑记忆正文的对话框；主题（topic）以只读形式展示，不可编辑。"""

    def __init__(self, content: str, topic: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑记忆内容")
        layout = QVBoxLayout(self)
        if topic:
            layout.addWidget(QLabel(f"当前主题（不可编辑）：{topic}"))
        else:
            layout.addWidget(QLabel("当前主题（不可编辑）：无"))
        layout.addWidget(QLabel("记忆内容："))
        self._text = QTextEdit()
        self._text.setPlainText(content)
        self._text.setMinimumHeight(120)
        layout.addWidget(self._text)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_content(self) -> str:
        return self._text.toPlainText()


class SettingsDialog(QDialog):
    """
    桌宠设置对话框类（模态窗口）
    使用 QTabWidget 组织不同类型的设置项。
    """
    def __init__(self, settings_manager, parent=None, long_term_memory=None):
        super().__init__(parent)
        self.sm = settings_manager
        # 长期记忆模块引用，由打开设置的一方传入（如 PetWindow/Tray），用于记忆管理标签页
        self._long_term_memory = long_term_memory

        self.setWindowTitle("桌宠设置")
        self.setWindowModality(Qt.ApplicationModal)
        
        # ========== 核心修改：启用窗口大小调整 ==========
        self.resize(500, 400)  # 设置初始大小
        self.setSizeGripEnabled(True)  # 右下角显示大小调整手柄
        
        self._build_ui()
        self._load_values()

    # ---------- UI 构建（核心修改：修复 QSizePolicy 调用） ----------
    def _build_ui(self):
        """构建对话框界面布局"""
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

        # 1.3 第三个标签：记忆管理（长期记忆列表、删除、清空）
        self.memory_tab = QWidget()
        self._build_memory_tab()
        self.tab_widget.addTab(self.memory_tab, "记忆管理")

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

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(10, 30)
        form.addRow("聊天框字体大小", self.font_size_spin)

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

        self.long_term_memory_cb = QCheckBox("启用长期记忆")
        form.addRow("长期记忆", self.long_term_memory_cb)

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

    # ---------- 记忆管理标签页 ----------
    def _build_memory_tab(self):
        layout = QVBoxLayout(self.memory_tab)
        self.memory_list = QListWidget()
        self.memory_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.memory_list.setMinimumHeight(200)
        layout.addWidget(QLabel("已存储的长期记忆（与用户相关的重要信息）："))
        layout.addWidget(self.memory_list)
        btn_row = QHBoxLayout()
        self.memory_refresh_btn = QPushButton("刷新列表")
        self.memory_edit_btn = QPushButton("编辑内容")
        self.memory_delete_btn = QPushButton("删除选中")
        self.memory_clear_btn = QPushButton("清空全部")
        self.memory_refresh_btn.clicked.connect(self._on_memory_refresh)
        self.memory_edit_btn.clicked.connect(self._on_memory_edit_content)
        self.memory_delete_btn.clicked.connect(self._on_memory_delete_one)
        self.memory_clear_btn.clicked.connect(self._on_memory_clear_all)
        btn_row.addWidget(self.memory_refresh_btn)
        btn_row.addWidget(self.memory_edit_btn)
        btn_row.addWidget(self.memory_delete_btn)
        btn_row.addWidget(self.memory_clear_btn)
        layout.addLayout(btn_row)
        layout.addStretch()
        # 初次加载列表
        self._on_memory_refresh()

    def _on_memory_refresh(self):
        """从长期记忆模块拉取列表并显示"""
        self.memory_list.clear()
        if not self._long_term_memory:
            self.memory_list.addItem(QListWidgetItem("（未连接长期记忆模块，请从主窗口打开设置）"))
            return
        try:
            items = self._long_term_memory.list_all()
            for it in items:
                topic_part = f"[{it.get('topic', '')}] " if it.get('topic') else ""
                text = f"#{it['id']} {topic_part}{it['content'][:80]}{'…' if len(it.get('content', '')) > 80 else ''}"
                row = QListWidgetItem(text)
                row.setData(Qt.UserRole, it["id"])
                self.memory_list.addItem(row)
            if not items:
                self.memory_list.addItem(QListWidgetItem("（暂无记忆）"))
        except Exception as e:
            self.memory_list.addItem(QListWidgetItem(f"（加载失败: {e}）"))

    def _on_memory_edit_content(self):
        """编辑选中记忆的文本内容（不编辑 topic）"""
        if not self._long_term_memory:
            return
        cur = self.memory_list.currentItem()
        if not cur:
            QMessageBox.information(self, "提示", "请先选中一条记忆")
            return
        id_val = cur.data(Qt.UserRole)
        if id_val is None:
            return
        id_int = int(id_val)
        mem = self._long_term_memory.get_by_id(id_int)
        if not mem:
            QMessageBox.warning(self, "错误", "该记忆不存在或已被删除")
            return
        dlg = _MemoryContentEditDialog(
            content=mem["content"],
            topic=mem.get("topic") or "",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_content = dlg.get_content()
        if not (new_content or "").strip():
            QMessageBox.warning(self, "提示", "内容不能为空")
            return
        try:
            ok = self._long_term_memory.update_content_by_id(id_int, new_content.strip())
            if ok:
                self._on_memory_refresh()
                QMessageBox.information(self, "提示", "已保存")
            else:
                QMessageBox.warning(self, "错误", "更新失败（可能 embedding 未就绪）")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"更新失败: {e}")

    def _on_memory_delete_one(self):
        """删除选中的一条记忆"""
        if not self._long_term_memory:
            return
        cur = self.memory_list.currentItem()
        if not cur:
            QMessageBox.information(self, "提示", "请先选中一条记忆")
            return
        id_val = cur.data(Qt.UserRole)
        if id_val is None:
            return
        if QMessageBox.Yes != QMessageBox.question(
            self, "确认", "确定要删除这条记忆吗？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ):
            return
        try:
            self._long_term_memory.delete_by_id(int(id_val))
            self._on_memory_refresh()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"删除失败: {e}")

    def _on_memory_clear_all(self):
        """清空全部记忆（二次确认）"""
        if not self._long_term_memory:
            return
        if QMessageBox.Yes != QMessageBox.question(
            self, "确认", "确定要清空全部长期记忆吗？此操作不可恢复。", QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ):
            return
        try:
            self._long_term_memory.clear_all()
            self._on_memory_refresh()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"清空失败: {e}")
    
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
        self.font_size_spin.setValue(self.sm.get("pet", "font_size", default=13))
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
        self.long_term_memory_cb.setChecked(
            self.sm.get("behavior", "long_term_memory_enabled", default=False)
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
        self.sm.set("pet", "scale", value=float(self.scale_spin.value()), save_now=False)
        self.sm.set("pet", "font_size", value=int(self.font_size_spin.value()), save_now=False)
        self.sm.set("behavior", "idle_interval_s", value=int(self.idle_spin.value()), save_now=False)
        self.sm.set("behavior", "screen_watch_enabled", value=self.screen_watch_cb.isChecked(), save_now=False)
        self.sm.set(
            "behavior", "screen_watch_interval_s", value=int(self.screen_watch_interval.value()), save_now=False
        )
        self.sm.set(
            "behavior", "temp_bubble_duration_s", value=int(self.temp_bubble_duration.value()), save_now=False
        )
        self.sm.set(
            "behavior", "long_term_memory_enabled", value=self.long_term_memory_cb.isChecked(), save_now=False
        )
        self.sm.set("user", "display_name", value=self.user_name.text().strip(), save_now=False)

        # 保存LLM设置
        self.sm.set("llm", "provider", value=self.provider_combo.currentText(), save_now=False)
        self.sm.set("llm", "api_key", value=self.llm_key.text().strip(), save_now=False)
        self.sm.set("llm", "base_url", value=self.base_url_edit.text().strip(), save_now=False)
        self.sm.set("llm", "model", value=self.model_edit.text().strip(), save_now=False)
        self.sm.set("llm", "max_tokens", value=int(self.max_tokens.value()), save_now=False)
        self.sm.set("llm", "history_rounds", value=int(self.history_spin.value()), save_now=False)
        self.sm.set("llm", "temperature", value=self.temperature_spinbox.value(), save_now=False)

        # 保存视觉模型设置
        vision_api_url = self.vision_api_url.text().strip().rstrip("/")
        # 补全 /v1/chat/completions 端点（兼容 openai 格式）
        if vision_api_url and not vision_api_url.endswith("/v1/chat/completions"):
            if vision_api_url.endswith("/v1"):
                vision_api_url = f"{vision_api_url}/chat/completions"
            else:
                vision_api_url = f"{vision_api_url}/v1/chat/completions"
        # 保存处理后的 URL
        self.sm.set("vision", "api_url", value=vision_api_url, save_now=False)
        self.sm.set("vision", "api_key", value=self.vision_api_key.text(), save_now=False)
        self.sm.set("vision", "model", value=self.vision_model.text(), save_now=False)

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