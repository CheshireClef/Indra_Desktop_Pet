# src/workers/screen_observer_worker.py
"""
屏幕观察工作线程
负责后台执行屏幕观察任务：
1. 截图 (ScreenObserver)
2. 视觉分析 (VisionClient)
3. 生成带情绪的评论 (ChatManager)
"""
from PySide6.QtCore import QThread, Signal

class ScreenObserveWorker(QThread):
    """
    屏幕观察异步线程
    避免在主线程执行耗时的 IO 和网络请求 (截图、LLM API 调用)。
    """
    finished = Signal(str, str)
    error = Signal(str)

    def __init__(self, observer, vision_client, chat_manager):
        super().__init__()
        self.observer = observer
        self.vision_client = vision_client
        self.chat_manager = chat_manager

    def run(self):
        """线程入口函数，按顺序执行观察流程"""
        try:
            # 1. 截图校验
            screenshot_path = self.observer.observe_once()
            if not screenshot_path or not screenshot_path.exists():
                raise Exception("截图失败：未生成有效文件")
            
            # 2. 视觉模型描述（describe_image 可能返回 None）
            description = self.vision_client.describe_image(screenshot_path)
            if description is None or not str(description).strip():
                raise Exception(
                    "视觉模型返回空描述，请检查是否选择了支持识图的多模态模型"
                )
            description = str(description).strip()
            
            # 3. 生成评论（reply 可能为 None，如 LLM 请求失败时）
            reply, emotion_tag = self.chat_manager.send_screen_observation_with_tag(description)
            if not reply or not reply.strip():
                raise Exception("未生成有效评论")

            self.finished.emit(reply, emotion_tag)  # 传递情绪标签
        except Exception as e:
            error_msg = f"屏幕观察出错：{str(e)}"
            print(f"[ScreenObserveWorker] {error_msg}")
            self.error.emit(error_msg)
