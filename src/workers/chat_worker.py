# src/workers/chat_worker.py
"""
用户聊天异步工作线程
在后台调用 ChatManager.chat_with_tag，避免阻塞聊天气泡 UI。
"""
from PySide6.QtCore import QThread, Signal


class ChatWorker(QThread):
    """后台执行一轮用户聊天（RAG + LLM HTTP）。"""

    success = Signal(str, str, object)  # reply, emotion_tag, reasoning
    failed = Signal(str)  # error_message

    def __init__(self, chat_manager, user_text: str):
        super().__init__()
        self._chat_manager = chat_manager
        self._user_text = user_text

    def run(self):
        try:
            reply, emotion_tag, error_message, reasoning = (
                self._chat_manager.chat_with_tag(self._user_text)
            )
            if error_message:
                self.failed.emit(error_message)
                return
            if not reply or not reply.strip():
                self.failed.emit("LLM 返回了空回复")
                return
            self.success.emit(reply.strip(), emotion_tag or "平常", reasoning)
        except Exception as e:
            print(f"[ChatWorker] {e}")
            self.failed.emit(f"聊天出错：{e}")
