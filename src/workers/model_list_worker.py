# src/workers/model_list_worker.py
"""
后台拉取 OpenAI 兼容 /v1/models 列表，避免阻塞设置界面。
"""
from PySide6.QtCore import QThread, Signal

from llm.providers.catalog import fetch_model_ids


class ModelListWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, base_url: str, api_key: str = ""):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key

    def run(self):
        try:
            ids = fetch_model_ids(self.base_url, self.api_key)
            if not ids:
                self.error.emit("未能获取模型列表，请检查 API Key 与 Base URL，或手动输入模型名")
                return
            self.finished.emit(ids)
        except Exception as e:
            self.error.emit(str(e))
