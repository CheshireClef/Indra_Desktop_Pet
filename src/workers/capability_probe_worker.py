# src/workers/capability_probe_worker.py
"""
后台探测模型 JSON / 识图能力，写入 settings capabilities_cache。
"""
from PySide6.QtCore import QThread, Signal

from llm.providers.capabilities import run_full_probe


class CapabilityProbeWorker(QThread):
    """探测单个模型能力。"""

    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, base_url: str, api_key: str, model: str):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def run(self):
        try:
            if not (self.model or "").strip():
                self.error.emit("请先选择或填写模型名")
                return
            result = run_full_probe(self.base_url, self.api_key, self.model)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class VisionProbeWorker(QThread):
    """仅探测识图能力。"""

    finished = Signal(bool, dict)
    error = Signal(str)

    def __init__(self, base_url: str, api_key: str, model: str):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def run(self):
        try:
            from llm.clients.openai_compatible import OpenAICompatibleClient
            from llm.clients.url_utils import normalize_base_url
            from llm.providers.capabilities import probe_vision
            from datetime import datetime, timezone

            base = normalize_base_url(self.base_url)
            client = OpenAICompatibleClient(base, self.api_key, self.model)
            from llm.clients.vision_adapter import match_vendor_id

            vendor_id = match_vendor_id(base)
            ok, meta = probe_vision(client, vendor_id=vendor_id)
            meta.setdefault("supports_vision", ok)
            meta["probed_at"] = datetime.now(timezone.utc).isoformat()
            self.finished.emit(ok, meta)
        except Exception as e:
            self.error.emit(str(e))
