# src/gui/memory_organize_dialog.py
"""
长期记忆手动整理：预览合并组与删除候选，确认后由 Worker 执行。
"""
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QCheckBox,
    QDialogButtonBox,
)


class MemoryOrganizePreviewDialog(QDialog):
    """展示 preview_organize 结果，用户确认后返回待执行的合并组与删除 id。"""

    def __init__(self, preview: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("整理记忆 — 预览")
        self.setMinimumSize(520, 420)
        self._preview = preview
        self._merge_group_ids: list[list[int]] = []
        self._delete_ids: list[int] = []

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "删除仅作用于您确认后的列表；勾选「永久保留」的条目不会出现在删除列表中。\n"
                "升级前旧记忆默认不删除，除非勾选下方选项。"
            )
        )

        self._include_legacy_cb = QCheckBox("将升级前且长期未使用的旧记忆也纳入删除候选")
        self._include_legacy_cb.setChecked(False)
        layout.addWidget(self._include_legacy_cb)

        layout.addWidget(QLabel("将执行的操作："))
        self._summary = QTextEdit()
        self._summary.setReadOnly(True)
        layout.addWidget(self._summary)

        btns = QDialogButtonBox()
        self._run_btn = btns.addButton("执行整理", QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._run_btn.clicked.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._apply_preview_text()

    def _apply_preview_text(self):
        p = self._preview
        merge_groups = p.get("merge_groups") or []
        deletes = list(p.get("delete_candidates") or [])
        legacy = list(p.get("legacy_delete_candidates") or []) if self._include_legacy_cb.isChecked() else []

        self._merge_group_ids = [g.get("ids") or [] for g in merge_groups if len(g.get("ids") or []) >= 2]
        self._delete_ids = [d["id"] for d in deletes + legacy]

        lines = [
            f"共 {p.get('total_count', 0)} 条记忆；已永久保留 {p.get('pinned_count', 0)} 条（不参与删除）。",
            "",
            f"【合并】{len(self._merge_group_ids)} 组（同主题 ≥2 条）：",
        ]
        for i, g in enumerate(merge_groups, 1):
            ids = g.get("ids") or []
            topic = g.get("topic") or "未分类"
            lines.append(f"  {i}. [{topic}] id={ids}")
            for it in (g.get("items") or [])[:5]:
                c = (it.get("content") or "")[:60]
                lines.append(f"      - #{it.get('id')}: {c}{'…' if len(it.get('content') or '') > 60 else ''}")
        lines.append("")
        lines.append(f"【删除】{len(self._delete_ids)} 条：")
        for d in deletes + legacy:
            reason = d.get("reason") or ""
            tag = {"duplicate": "重复", "idle_unreferenced": "闲置未引用", "legacy_idle": "升级前闲置"}.get(
                reason, reason
            )
            c = (d.get("content") or "")[:70]
            lines.append(f"  - #{d.get('id')} ({tag}): {c}{'…' if len(d.get('content') or '') > 70 else ''}")

        if not self._merge_group_ids and not self._delete_ids:
            lines.append("（无需合并或删除，可取消）")
            self._run_btn.setEnabled(False)
        else:
            self._run_btn.setEnabled(True)

        self._summary.setPlainText("\n".join(lines))

    def _on_accept(self):
        if not self._merge_group_ids and not self._delete_ids:
            self.reject()
            return
        self.accept()

    def get_plan(self) -> tuple[list[list[int]], list[int]]:
        return self._merge_group_ids, self._delete_ids

    def refresh_preview(self, preview: dict):
        """勾选遗留选项后由外部重新 preview 并刷新"""
        self._preview = preview
        self._apply_preview_text()
