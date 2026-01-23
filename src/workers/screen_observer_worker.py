from PySide6.QtCore import QThread, Signal

class ScreenObserveWorker(QThread):
    finished = Signal(str, str)
    error = Signal(str)

    def __init__(self, observer, vision_client, chat_manager):
        super().__init__()
        self.observer = observer
        self.vision_client = vision_client
        self.chat_manager = chat_manager

    def run(self):
        try:
            # 1. 截图校验
            screenshot_path = self.observer.observe_once()
            if not screenshot_path or not screenshot_path.exists():
                raise Exception("截图失败：未生成有效文件")
            
            # 2. 视觉模型描述
            description = self.vision_client.describe_image(screenshot_path)
            if not description.strip():
                raise Exception("视觉模型返回空描述")
            
            # 3. 生成评论
            reply, emotion_tag = self.chat_manager.send_screen_observation_with_tag(description)
            if not reply.strip():
                raise Exception("未生成有效评论")

            self.finished.emit(reply, emotion_tag)  # 传递情绪标签
        except Exception as e:
            error_msg = f"屏幕观察出错：{str(e)}"
            print(f"[ScreenObserveWorker] {error_msg}")
            self.error.emit(error_msg)
