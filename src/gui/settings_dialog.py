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

from llm.clients.url_utils import normalize_base_url
from llm.providers.catalog import filter_vision_candidates
from llm.providers.registry import default_base_url, list_vendor_ids, vendor_label
from workers.capability_probe_worker import CapabilityProbeWorker, VisionProbeWorker
from workers.model_list_worker import ModelListWorker
from workers.memory_organize_worker import MemoryOrganizeWorker
from .memory_organize_dialog import MemoryOrganizePreviewDialog


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
        self._memory_organize_worker = None
        self._memory_list_refreshing = False

        self.setWindowTitle("桌宠设置")
        self.setWindowModality(Qt.ApplicationModal)
        
        # ========== 核心修改：启用窗口大小调整 ==========
        self.resize(500, 400)  # 设置初始大小
        self.setSizeGripEnabled(True)  # 右下角显示大小调整手柄
        
        self._model_list_worker = None
        self._capability_probe_worker = None
        self._vision_probe_worker = None
        self._chat_cached_model_ids: list[str] = []
        self._vision_cached_model_ids: list[str] = []

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

        self.long_term_memory_cb = QCheckBox("启用长期记忆")
        form.addRow(self.long_term_memory_cb)

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

    def _append_api_connection_form(self, form: QFormLayout, *, prefix: str):
        """向表单追加一组 API 连接控件（chat / vision）。"""
        vendor_combo = QComboBox()
        for vid in list_vendor_ids():
            vendor_combo.addItem(vendor_label(vid), vid)
        base_url_edit = QLineEdit()
        api_key_edit = QLineEdit()
        api_key_edit.setEchoMode(QLineEdit.Password)
        btn_test = QPushButton("测试连接")
        btn_refresh = QPushButton("刷新模型列表")
        status_label = QLabel("状态：未连接")
        status_label.setWordWrap(True)

        if prefix == "chat":
            vendor_combo.currentIndexChanged.connect(
                lambda: self._on_vendor_changed(vendor_combo, base_url_edit)
            )
            btn_test.clicked.connect(self._on_test_connection)
            btn_refresh.clicked.connect(self._on_refresh_chat_models)
            self.chat_vendor_combo = vendor_combo
            self.chat_base_url_edit = base_url_edit
            self.chat_api_key_edit = api_key_edit
            self.chat_btn_test_connection = btn_test
            self.chat_btn_refresh_models = btn_refresh
            self.chat_connection_status_label = status_label
        else:
            vendor_combo.currentIndexChanged.connect(
                lambda: self._on_vendor_changed(vendor_combo, base_url_edit)
            )
            btn_test.clicked.connect(self._on_test_vision_connection)
            btn_refresh.clicked.connect(self._on_refresh_vision_models)
            self.vision_vendor_combo = vendor_combo
            self.vision_base_url_edit = base_url_edit
            self.vision_api_key_edit = api_key_edit
            self.vision_btn_test_connection = btn_test
            self.vision_btn_refresh_models = btn_refresh
            self.vision_connection_status_label = status_label
            self._vision_api_widgets = [
                vendor_combo,
                base_url_edit,
                api_key_edit,
                btn_test,
                btn_refresh,
            ]

        form.addRow("服务商", vendor_combo)
        form.addRow("Base URL", base_url_edit)
        form.addRow("API Key", api_key_edit)
        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_test)
        btn_row.addWidget(btn_refresh)
        form.addRow(btn_row)
        form.addRow(status_label)

    # ---------- 构建模型设置标签页（对话/识图各自含 API 连接，识图可共用对话连接） ----------
    def _build_model_tab(self):
        layout = QVBoxLayout(self.model_tab)

        chat_group = QGroupBox("对话模型")
        chat_form = QFormLayout(chat_group)
        self._append_api_connection_form(chat_form, prefix="chat")

        self.chat_model_combo = QComboBox()
        self.chat_model_combo.setEditable(True)
        chat_form.addRow("模型", self.chat_model_combo)

        self.output_mode_combo = QComboBox()
        self.output_mode_combo.addItem("自动（推荐）", "auto")
        self.output_mode_combo.addItem("优先 JSON 结构化", "json_preferred")
        self.output_mode_combo.addItem("仅自然语言", "natural_only")
        chat_form.addRow("回复格式", self.output_mode_combo)

        self.temperature_spinbox = QDoubleSpinBox(self)
        self.temperature_spinbox.setRange(0.0, 1.5)
        self.temperature_spinbox.setSingleStep(0.1)
        chat_form.addRow("Temperature", self.temperature_spinbox)

        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(16, 8192)
        chat_form.addRow("Max Tokens", self.max_tokens)

        self.history_spin = QSpinBox()
        self.history_spin.setRange(1, 100)
        chat_form.addRow("保留对话轮数", self.history_spin)

        layout.addWidget(chat_group)

        vision_group = QGroupBox("屏幕识图模型")
        vision_form = QFormLayout(vision_group)

        self.same_connection_cb = QCheckBox("与上方使用同一 API 连接")
        self.same_connection_cb.setChecked(True)
        self.same_connection_cb.stateChanged.connect(self._on_same_connection_changed)
        vision_form.addRow(self.same_connection_cb)

        self._append_api_connection_form(vision_form, prefix="vision")

        self.vision_model_combo = QComboBox()
        self.vision_model_combo.setEditable(True)
        vision_form.addRow("模型", self.vision_model_combo)

        self.vision_show_all_cb = QCheckBox("显示全部模型（不过滤多模态）")
        self.vision_show_all_cb.stateChanged.connect(self._refill_vision_combo)
        vision_form.addRow(self.vision_show_all_cb)

        self.btn_test_vision = QPushButton("测试识图")
        self.btn_test_vision.clicked.connect(self._on_test_vision)
        vision_form.addRow(self.btn_test_vision)

        self.vision_status_label = QLabel("")
        self.vision_status_label.setWordWrap(True)
        vision_form.addRow(self.vision_status_label)

        layout.addWidget(vision_group)
        layout.addStretch()

        # 共用连接时，对话侧 API 变更实时镜像到识图侧（识图区灰显）
        self.chat_vendor_combo.currentIndexChanged.connect(self._maybe_sync_vision_from_chat)
        self.chat_base_url_edit.textChanged.connect(self._maybe_sync_vision_from_chat)
        self.chat_api_key_edit.textChanged.connect(self._maybe_sync_vision_from_chat)

    # ---------- 记忆管理标签页 ----------
    def _build_memory_tab(self):
        layout = QVBoxLayout(self.memory_tab)
        layout.addWidget(
            QLabel(
                "已存储的长期记忆。勾选左侧框表示「永久保留」，整理时不会删除该条。"
            )
        )
        self.memory_list = QListWidget()
        self.memory_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.memory_list.setMinimumHeight(200)
        self.memory_list.itemChanged.connect(self._on_memory_item_pin_changed)
        layout.addWidget(self.memory_list)
        btn_row = QHBoxLayout()
        self.memory_refresh_btn = QPushButton("刷新列表")
        self.memory_edit_btn = QPushButton("编辑内容")
        self.memory_delete_btn = QPushButton("删除选中")
        self.memory_clear_btn = QPushButton("清空全部")
        self.memory_organize_btn = QPushButton("整理全部记忆")
        self.memory_organize_status = QLabel("")
        self.memory_refresh_btn.clicked.connect(self._on_memory_refresh)
        self.memory_edit_btn.clicked.connect(self._on_memory_edit_content)
        self.memory_delete_btn.clicked.connect(self._on_memory_delete_one)
        self.memory_clear_btn.clicked.connect(self._on_memory_clear_all)
        self.memory_organize_btn.clicked.connect(self._on_memory_organize)
        btn_row.addWidget(self.memory_refresh_btn)
        btn_row.addWidget(self.memory_edit_btn)
        btn_row.addWidget(self.memory_delete_btn)
        btn_row.addWidget(self.memory_clear_btn)
        btn_row.addWidget(self.memory_organize_btn)
        layout.addLayout(btn_row)
        layout.addWidget(self.memory_organize_status)
        layout.addStretch()
        self._on_memory_refresh()

    def _on_memory_refresh(self):
        """从长期记忆模块拉取列表并显示"""
        self._memory_list_refreshing = True
        self.memory_list.clear()
        if not self._long_term_memory:
            self.memory_list.addItem(QListWidgetItem("（未连接长期记忆模块，请从主窗口打开设置）"))
            self._memory_list_refreshing = False
            return
        try:
            items = self._long_term_memory.list_all()
            for it in items:
                topic_part = f"[{it.get('topic', '')}] " if it.get('topic') else ""
                rc = it.get("ref_count")
                rc_tag = "遗留" if rc is None else f"引用{rc}"
                pin_tag = "[保留] " if it.get("pinned") else ""
                text = (
                    f"{pin_tag}#{it['id']} ({rc_tag}) {topic_part}"
                    f"{it['content'][:72]}{'…' if len(it.get('content', '')) > 72 else ''}"
                )
                row = QListWidgetItem(text)
                row.setData(Qt.UserRole, it["id"])
                row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                row.setCheckState(
                    Qt.CheckState.Checked if it.get("pinned") else Qt.CheckState.Unchecked
                )
                self.memory_list.addItem(row)
            if not items:
                self.memory_list.addItem(QListWidgetItem("（暂无记忆）"))
        except Exception as e:
            self.memory_list.addItem(QListWidgetItem(f"（加载失败: {e}）"))
        finally:
            self._memory_list_refreshing = False

    def _on_memory_item_pin_changed(self, item: QListWidgetItem):
        """勾选变更 → 写入 pinned"""
        if self._memory_list_refreshing or not self._long_term_memory:
            return
        id_val = item.data(Qt.UserRole)
        if id_val is None:
            return
        pinned = item.checkState() == Qt.CheckState.Checked
        try:
            ok = self._long_term_memory.set_pinned(int(id_val), pinned)
            if not ok:
                raise RuntimeError("更新失败")
        except Exception as e:
            self._memory_list_refreshing = True
            item.setCheckState(
                Qt.CheckState.Checked if pinned else Qt.CheckState.Unchecked
            )
            self._memory_list_refreshing = False
            QMessageBox.warning(self, "错误", f"永久保留标记保存失败: {e}")

    def _can_run_memory_organize(self) -> tuple[bool, str]:
        if not self._long_term_memory:
            return False, "未连接长期记忆模块"
        if not self._long_term_memory.is_merge_llm_available():
            return False, "长期记忆未配置 LLM 合并能力"
        binding = self.sm.get_chat_binding()
        if not binding.get("model") or not binding.get("base_url"):
            return False, "请先在「模型设置」中配置与聊天相同的 API（模型与 Base URL）"
        return True, ""

    def _set_memory_tab_busy(self, busy: bool):
        for w in (
            self.memory_refresh_btn,
            self.memory_edit_btn,
            self.memory_delete_btn,
            self.memory_clear_btn,
            self.memory_organize_btn,
            self.memory_list,
        ):
            w.setEnabled(not busy)
        self.memory_organize_status.setText("整理中，请稍候…" if busy else "")

    def _on_memory_organize(self):
        """预览后确认，后台执行整理"""
        ok, msg = self._can_run_memory_organize()
        if not ok:
            QMessageBox.information(self, "无法整理", msg)
            return
        if self._memory_organize_worker and self._memory_organize_worker.isRunning():
            QMessageBox.information(self, "提示", "整理正在进行中")
            return
        try:
            preview = self._long_term_memory.preview_organize(include_legacy=False)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"生成预览失败: {e}")
            return
        dlg = MemoryOrganizePreviewDialog(preview, parent=self)

        def on_legacy_toggled(_state):
            try:
                p2 = self._long_term_memory.preview_organize(
                    include_legacy=dlg._include_legacy_cb.isChecked()
                )
                dlg.refresh_preview(p2)
            except Exception as ex:
                QMessageBox.warning(self, "错误", f"刷新预览失败: {ex}")

        dlg._include_legacy_cb.stateChanged.connect(on_legacy_toggled)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        merge_ids, delete_ids = dlg.get_plan()
        if not merge_ids and not delete_ids:
            return
        self._set_memory_tab_busy(True)
        self._memory_organize_worker = MemoryOrganizeWorker(
            self._long_term_memory,
            merge_group_ids=merge_ids,
            delete_ids=delete_ids,
        )
        self._memory_organize_worker.finished.connect(self._on_memory_organize_finished)
        self._memory_organize_worker.error.connect(self._on_memory_organize_error)
        self._memory_organize_worker.start()

    def _on_memory_organize_finished(self, stats: dict):
        self._set_memory_tab_busy(False)
        self._on_memory_refresh()
        err = stats.get("errors") or []
        err_txt = "\n".join(err[:5]) if err else ""
        QMessageBox.information(
            self,
            "整理完成",
            f"合并 {stats.get('merged_groups', 0)} 组（共 {stats.get('merged_from_rows', 0)} 条并入），"
            f"删除 {stats.get('deleted_count', 0)} 条。"
            + (f"\n\n部分提示：\n{err_txt}" if err_txt else ""),
        )

    def _on_memory_organize_error(self, msg: str):
        self._set_memory_tab_busy(False)
        QMessageBox.warning(self, "整理失败", msg)

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
    
    def _vendor_id_from_combo(self, combo: QComboBox) -> str:
        vid = combo.currentData()
        return vid if vid else "custom_openai"

    def _chat_connection_fields(self) -> tuple[str, str, str]:
        return (
            self.chat_base_url_edit.text().strip(),
            self.chat_api_key_edit.text().strip(),
            self._vendor_id_from_combo(self.chat_vendor_combo),
        )

    def _vision_connection_fields(self) -> tuple[str, str, str]:
        """识图所用连接：勾选共用对话时取对话侧字段。"""
        if self.same_connection_cb.isChecked():
            return self._chat_connection_fields()
        return (
            self.vision_base_url_edit.text().strip(),
            self.vision_api_key_edit.text().strip(),
            self._vendor_id_from_combo(self.vision_vendor_combo),
        )

    def _on_vendor_changed(self, vendor_combo: QComboBox, base_url_edit: QLineEdit):
        vid = self._vendor_id_from_combo(vendor_combo)
        if vid != "custom_openai":
            base_url_edit.setText(default_base_url(vid))

    def _maybe_sync_vision_from_chat(self):
        if self.same_connection_cb.isChecked():
            self._sync_vision_api_from_chat()

    def _on_same_connection_changed(self):
        same = self.same_connection_cb.isChecked()
        self._set_vision_api_enabled(not same)
        if same:
            self._sync_vision_api_from_chat()

    def _set_vision_api_enabled(self, enabled: bool):
        for w in getattr(self, "_vision_api_widgets", []):
            w.setEnabled(enabled)

    def _sync_vision_api_from_chat(self):
        """将对话侧 API 连接同步到识图侧（共用连接时展示为灰显只读镜像）。"""
        self.vision_vendor_combo.blockSignals(True)
        self.vision_base_url_edit.blockSignals(True)
        self.vision_api_key_edit.blockSignals(True)
        self.vision_vendor_combo.setCurrentIndex(self.chat_vendor_combo.currentIndex())
        self.vision_base_url_edit.setText(self.chat_base_url_edit.text())
        self.vision_api_key_edit.setText(self.chat_api_key_edit.text())
        self.vision_vendor_combo.blockSignals(False)
        self.vision_base_url_edit.blockSignals(False)
        self.vision_api_key_edit.blockSignals(False)

    def _fill_model_combo(self, combo: QComboBox, model_id: str, ids: list[str]):
        combo.blockSignals(True)
        combo.clear()
        for mid in ids:
            combo.addItem(mid)
        if model_id:
            idx = combo.findText(model_id)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.addItem(model_id)
                combo.setCurrentText(model_id)
        combo.blockSignals(False)

    def _refill_vision_combo(self):
        ids = getattr(self, "_vision_cached_model_ids", None) or getattr(
            self, "_chat_cached_model_ids", []
        )
        current = self.vision_model_combo.currentText()
        self._refill_vision_combo_from_ids(ids, current)

    def _on_refresh_chat_models(self):
        base, key, _vid = self._chat_connection_fields()
        base = normalize_base_url(base)
        if not base:
            QMessageBox.warning(self, "提示", "请先填写 Base URL")
            return
        self.chat_connection_status_label.setText("状态：正在拉取模型列表…")
        self.chat_btn_refresh_models.setEnabled(False)
        self._chat_model_list_worker = ModelListWorker(base, key)
        self._chat_model_list_worker.finished.connect(self._on_chat_model_list_finished)
        self._chat_model_list_worker.error.connect(self._on_chat_model_list_error)
        self._chat_model_list_worker.start()

    def _on_chat_model_list_finished(self, ids: list):
        self.chat_btn_refresh_models.setEnabled(True)
        self._chat_cached_model_ids = ids
        chat_model = self.chat_model_combo.currentText()
        self._fill_model_combo(self.chat_model_combo, chat_model, ids)
        if self.same_connection_cb.isChecked():
            self._vision_cached_model_ids = ids
            self._refill_vision_combo()
        self.chat_connection_status_label.setText(f"状态：已获取 {len(ids)} 个模型")

    def _on_chat_model_list_error(self, msg: str):
        self.chat_btn_refresh_models.setEnabled(True)
        self.chat_connection_status_label.setText(f"状态：{msg}")

    def _on_refresh_vision_models(self):
        base, key, _vid = self._vision_connection_fields()
        base = normalize_base_url(base)
        if not base:
            QMessageBox.warning(self, "提示", "请先填写 Base URL")
            return
        self.vision_connection_status_label.setText("状态：正在拉取模型列表…")
        self.vision_btn_refresh_models.setEnabled(False)
        self._vision_model_list_worker = ModelListWorker(base, key)
        self._vision_model_list_worker.finished.connect(self._on_vision_model_list_finished)
        self._vision_model_list_worker.error.connect(self._on_vision_model_list_error)
        self._vision_model_list_worker.start()

    def _on_vision_model_list_finished(self, ids: list):
        self.vision_btn_refresh_models.setEnabled(True)
        self._vision_cached_model_ids = ids
        vision_model = self.vision_model_combo.currentText()
        self._refill_vision_combo_from_ids(ids, vision_model)
        self.vision_connection_status_label.setText(f"状态：已获取 {len(ids)} 个模型")

    def _on_vision_model_list_error(self, msg: str):
        self.vision_btn_refresh_models.setEnabled(True)
        self.vision_connection_status_label.setText(f"状态：{msg}")

    def _refill_vision_combo_from_ids(self, ids: list, current: str):
        if ids and not self.vision_show_all_cb.isChecked():
            ids = filter_vision_candidates(ids)
        self._fill_model_combo(self.vision_model_combo, current, ids)

    def _on_test_connection(self):
        base, key, vid = self._chat_connection_fields()
        base = normalize_base_url(base)
        model = self.chat_model_combo.currentText().strip()
        if not base:
            QMessageBox.warning(self, "提示", "请先填写 Base URL")
            return
        if not model:
            QMessageBox.warning(self, "提示", "请先选择或填写对话模型名")
            return
        self.chat_connection_status_label.setText("状态：正在测试连接并探测能力…")
        self.chat_btn_test_connection.setEnabled(False)
        self._capability_probe_worker = CapabilityProbeWorker(base, key, model)
        self._capability_probe_worker.finished.connect(self._on_chat_probe_finished)
        self._capability_probe_worker.error.connect(self._on_chat_probe_error)
        self._capability_probe_worker.start()

    def _on_chat_probe_finished(self, result: dict):
        self.chat_btn_test_connection.setEnabled(True)
        model = self.chat_model_combo.currentText().strip()
        conn_id = "default"
        self.sm.set_capability_cache(conn_id, model, result, save_now=False)
        jm = result.get("json_mode", "?")
        sv = "支持" if result.get("supports_vision") else "不支持"
        self.chat_connection_status_label.setText(
            f"状态：连接成功 | JSON 模式={jm} | 该模型识图探测={sv}"
        )
        QMessageBox.information(
            self,
            "测试连接",
            f"对话模型探测完成。\nJSON 输出：{jm}\n识图（该模型）：{sv}",
        )

    def _on_chat_probe_error(self, msg: str):
        self.chat_btn_test_connection.setEnabled(True)
        self.chat_connection_status_label.setText(f"状态：失败 - {msg}")
        QMessageBox.warning(self, "探测失败", msg)

    def _on_test_vision_connection(self):
        base, key, _vid = self._vision_connection_fields()
        base = normalize_base_url(base)
        model = self.vision_model_combo.currentText().strip()
        if not base:
            QMessageBox.warning(self, "提示", "请先填写 Base URL")
            return
        if not model:
            QMessageBox.warning(self, "提示", "请先选择或填写识图模型名")
            return
        self.vision_connection_status_label.setText("状态：正在测试连接…")
        self.vision_btn_test_connection.setEnabled(False)
        self._vision_conn_probe_worker = VisionProbeWorker(base, key, model)
        self._vision_conn_probe_worker.finished.connect(self._on_vision_conn_probe_finished)
        self._vision_conn_probe_worker.error.connect(self._on_vision_conn_probe_error)
        self._vision_conn_probe_worker.start()

    def _on_vision_conn_probe_finished(self, ok: bool, meta: dict):
        self.vision_btn_test_connection.setEnabled(True)
        conn_id = "vision" if not self.same_connection_cb.isChecked() else "default"
        model = self.vision_model_combo.currentText().strip()
        existing = self.sm.get_capability_cache(conn_id, model) or {}
        existing.update(meta)
        existing["supports_vision"] = ok
        self.sm.set_capability_cache(conn_id, model, existing, save_now=False)
        if ok:
            self.vision_connection_status_label.setText("状态：连接成功，识图可用。")
            QMessageBox.information(self, "测试连接", "识图 API 连接测试通过。")
        else:
            note = (meta.get("probe_note") or "").strip()
            self.vision_connection_status_label.setText(
                "状态：连接成功，但识图探测未通过。"
                + (f" ({note[:60]}…)" if note else "")
            )
            QMessageBox.warning(
                self,
                "测试连接",
                "已连通 API，但识图探测未通过（已自动尝试多种参数）。"
                + (f"\n\n{note}" if note else ""),
            )

    def _on_vision_conn_probe_error(self, msg: str):
        self.vision_btn_test_connection.setEnabled(True)
        self.vision_connection_status_label.setText(f"状态：失败 - {msg}")
        QMessageBox.warning(self, "探测失败", msg)

    def _on_test_vision(self):
        base, key, _ = self._vision_connection_fields()
        base = normalize_base_url(base)
        model = self.vision_model_combo.currentText().strip()
        if not base:
            QMessageBox.warning(self, "提示", "请先填写 Base URL")
            return
        if not model:
            QMessageBox.warning(self, "提示", "请先选择或填写识图模型名")
            return
        self.vision_status_label.setText("正在测试识图…")
        self.btn_test_vision.setEnabled(False)
        self._vision_probe_worker = VisionProbeWorker(base, key, model)
        self._vision_probe_worker.finished.connect(self._on_vision_probe_finished)
        self._vision_probe_worker.error.connect(self._on_vision_probe_error)
        self._vision_probe_worker.start()

    def _on_vision_probe_finished(self, ok: bool, meta: dict):
        self.btn_test_vision.setEnabled(True)
        conn_id = "vision" if not self.same_connection_cb.isChecked() else "default"
        model = self.vision_model_combo.currentText().strip()
        existing = self.sm.get_capability_cache(conn_id, model) or {}
        existing.update(meta)
        existing["supports_vision"] = ok
        self.sm.set_capability_cache(conn_id, model, existing, save_now=False)
        if ok:
            self.vision_status_label.setText("识图测试通过，可使用屏幕监视功能。")
            QMessageBox.information(self, "测试识图", "识图测试通过。")
        else:
            note = (meta.get("probe_note") or "").strip()
            hint = f"\n\n详情：{note}" if note else ""
            self.vision_status_label.setText(
                "识图测试未通过：请查看终端 [VisionAdapter] 日志或更换 VL 类模型。"
            )
            QMessageBox.warning(
                self,
                "测试识图",
                "当前模型未完成识图探测（已自动尝试多种请求参数）。"
                "请选用名称含 VL/Vision 的多模态模型，或查看终端日志。"
                f"{hint}",
            )

    def _on_vision_probe_error(self, msg: str):
        self.btn_test_vision.setEnabled(True)
        self.vision_status_label.setText(f"测试失败：{msg}")
        QMessageBox.warning(self, "测试识图", msg)

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

        chat_b = self.sm.get_chat_binding()
        models = self.sm.get_models_block()
        vision_cfg = models.get("vision") or {}
        same_conn = vision_cfg.get("same_connection_as_chat", True)
        self.same_connection_cb.setChecked(same_conn)

        chat_vendor = chat_b.get("vendor", "siliconflow")
        cidx = self.chat_vendor_combo.findData(chat_vendor)
        if cidx >= 0:
            self.chat_vendor_combo.setCurrentIndex(cidx)
        self.chat_base_url_edit.setText(chat_b.get("base_url") or "")
        self.chat_api_key_edit.setText(chat_b.get("api_key") or "")
        self._fill_model_combo(self.chat_model_combo, chat_b.get("model") or "", [])

        if same_conn:
            self._sync_vision_api_from_chat()
        else:
            conn_id = vision_cfg.get("connection_id", "vision")
            conn = next(
                (c for c in (models.get("connections") or []) if c.get("id") == conn_id),
                {},
            )
            v_vendor = conn.get("vendor", "siliconflow")
            vidx = self.vision_vendor_combo.findData(v_vendor)
            if vidx >= 0:
                self.vision_vendor_combo.setCurrentIndex(vidx)
            self.vision_base_url_edit.setText(conn.get("base_url") or "")
            self.vision_api_key_edit.setText(conn.get("api_key") or "")

        vision_b = self.sm.get_vision_binding()
        self._fill_model_combo(
            self.vision_model_combo,
            vision_b.get("model") or "Qwen/Qwen3-VL-32B-Instruct",
            [],
        )
        self._set_vision_api_enabled(not same_conn)

        om = chat_b.get("output_mode", "auto")
        oidx = self.output_mode_combo.findData(om)
        if oidx >= 0:
            self.output_mode_combo.setCurrentIndex(oidx)
        self.temperature_spinbox.setValue(float(chat_b.get("temperature", 1.0)))
        self.max_tokens.setValue(int(chat_b.get("max_tokens", 512)))
        self.history_spin.setValue(int(chat_b.get("history_rounds", 10)))

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

        # 屏幕监视 + 识图能力警告
        vision_model = self.vision_model_combo.currentText().strip()
        vision_conn_id = (
            "default" if self.same_connection_cb.isChecked() else "vision"
        )
        cache = self.sm.get_capability_cache(vision_conn_id, vision_model) or {}
        if self.screen_watch_cb.isChecked() and cache.get("supports_vision") is False:
            if QMessageBox.Yes != QMessageBox.question(
                self,
                "识图模型可能不可用",
                "当前识图模型探测为不支持多模态，屏幕监视可能失败。\n是否仍要保存并启用屏幕监视？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            ):
                return

        self._save_models_to_settings(save_now=False)
        from llm.model_service import ModelService

        ModelService.reset_cache()
        self.sm.save()
        self.accept()

    def _save_models_to_settings(self, save_now: bool = True):
        """写入 models v2，并同步 legacy llm/vision 投影。"""
        models = self.sm.get_models_block()
        chat_vendor = self._vendor_id_from_combo(self.chat_vendor_combo)
        chat_base = normalize_base_url(self.chat_base_url_edit.text().strip())
        chat_key = self.chat_api_key_edit.text().strip()
        chat_model = self.chat_model_combo.currentText().strip()
        vision_model = self.vision_model_combo.currentText().strip()
        same_conn = self.same_connection_cb.isChecked()

        chat_conn = {
            "id": "default",
            "vendor": chat_vendor,
            "protocol": "openai_compatible",
            "base_url": chat_base,
            "api_key": chat_key,
        }
        connections = [chat_conn]
        vision_conn_id = "default"
        if not same_conn:
            vision_vendor = self._vendor_id_from_combo(self.vision_vendor_combo)
            vision_conn = {
                "id": "vision",
                "vendor": vision_vendor,
                "protocol": "openai_compatible",
                "base_url": normalize_base_url(self.vision_base_url_edit.text().strip()),
                "api_key": self.vision_api_key_edit.text().strip(),
            }
            connections.append(vision_conn)
            vision_conn_id = "vision"

        models["schema_version"] = 2
        models["connections"] = connections
        models["chat"] = {
            "connection_id": "default",
            "model": chat_model,
            "temperature": float(self.temperature_spinbox.value()),
            "max_tokens": int(self.max_tokens.value()),
            "history_rounds": int(self.history_spin.value()),
            "output_mode": self.output_mode_combo.currentData() or "auto",
        }
        models["vision"] = {
            "same_connection_as_chat": same_conn,
            "connection_id": vision_conn_id,
            "model": vision_model or "Qwen/Qwen3-VL-32B-Instruct",
        }
        self.sm._sync_legacy_from_models()
        if save_now:
            from llm.model_service import ModelService
            ModelService.reset_cache()
            self.sm.save()