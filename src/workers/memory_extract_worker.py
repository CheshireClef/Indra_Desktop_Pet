# src/workers/memory_extract_worker.py
"""
聊天结束后异步抽取长期记忆，不阻塞主界面与对话气泡。
"""
from __future__ import annotations

import copy

from PySide6.QtCore import QThread, Signal

from llm.memory_extract import run_memory_extract


class MemoryExtractWorker(QThread):
    """在后台线程调用记忆模型，将结果写入 LongTermMemory。"""

    finished = Signal(int, int)  # written_count, generation_id
    error = Signal(str, int)  # message, generation_id

    def __init__(
        self,
        *,
        settings_manager,
        long_term_memory,
        history_slice: list[dict],
        generation_id: int,
    ):
        super().__init__()
        self._sm = settings_manager
        self._ltm = long_term_memory
        self._history_slice = copy.deepcopy(history_slice)
        self._generation_id = generation_id

    def run(self):
        try:
            if not self._sm.get("behavior", "long_term_memory_enabled", default=False):
                self.finished.emit(0, self._generation_id)
                return
            if not self._ltm:
                self.finished.emit(0, self._generation_id)
                return

            items = run_memory_extract(self._history_slice, self._sm)
            written = 0
            for content, topic in items:
                try:
                    self._ltm.add_or_update(content, topic=topic)
                    written += 1
                except Exception as e:
                    print(f"[MemoryExtract] 写入失败: {e}")
            if written:
                print(f"[MemoryExtract] 已写入 {written} 条")
            self.finished.emit(written, self._generation_id)
        except Exception as e:
            self.error.emit(str(e), self._generation_id)
