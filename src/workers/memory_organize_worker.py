# src/workers/memory_organize_worker.py
"""
后台执行长期记忆手动整理（合并 + 删除），避免阻塞设置界面。
"""
from PySide6.QtCore import QThread, Signal
from typing import Any, List, Optional


class MemoryOrganizeWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        long_term_memory: Any,
        *,
        merge_group_ids: Optional[List[List[int]]] = None,
        delete_ids: Optional[List[int]] = None,
    ):
        super().__init__()
        self._ltm = long_term_memory
        self._merge_group_ids = merge_group_ids or []
        self._delete_ids = delete_ids or []

    def run(self):
        try:
            if not self._ltm:
                self.error.emit("长期记忆模块未连接")
                return
            stats = self._ltm.run_organize(
                merge_group_ids=self._merge_group_ids,
                delete_ids=self._delete_ids,
            )
            self.finished.emit(stats)
        except Exception as e:
            self.error.emit(str(e))
