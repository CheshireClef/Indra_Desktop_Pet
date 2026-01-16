# src/gui/animation.py
from PySide6.QtCore import QTimer, QObject, Signal  # 新增 Signal 导入
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
import os
from utils import resource_path

BASE_SIZE = 256  # ⭐ 逻辑基准尺寸（与你原来的 pet.png 一致）


class AnimationDriver(QObject):
    """
    AnimationDriver
    - 管理所有动画帧
    - 只负责“怎么播”，不关心“什么时候播”
    """
    idle_frames_loaded = Signal()

    def __init__(self, target_label):
        super().__init__()
        self.target = target_label

        self.animations: dict[str, list[QPixmap]] = {}
        self.state: str | None = None

        self.frames: list[QPixmap] = []
        self.frame_index = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next_frame)

        # 预加载 idle 动画
        self._load_idle_frames()
        # 触发加载完成信号
        self.idle_frames_loaded.emit()
        # 新增：获取 idle 动画第一帧
        def get_idle_first_frame(self):
            """获取idle动画的第一帧（用于初始显示）"""
            idle_frames = self.animations.get("idle")
            if idle_frames and len(idle_frames) > 0:
                return idle_frames[0]
            return None
        
    def get_idle_first_frame(self):
        """获取idle动画的第一帧（用于初始显示）"""
        idle_frames = self.animations.get("idle")
        if idle_frames and len(idle_frames) > 0:
            return idle_frames[0]
        return None
    # -------------------------------------------------
    # loading
    # -------------------------------------------------

    def _load_idle_frames(self):
        """
        加载 idle 动画：
        - 原始资源是 1280x1280
        - 先缩放到 256x256
        - 再按当前 label 尺寸等比缩放
        """
        folder = resource_path("assets/images/idle")
        if not os.path.isdir(folder):
            return

        files = sorted(
            f for f in os.listdir(folder)
            if f.lower().endswith(".png")
        )

        frames: list[QPixmap] = []
        for f in files:
            pix_path = resource_path(f"assets/images/idle/{f}")
            pix = QPixmap(pix_path)
            if pix.isNull():
                continue

            # ① 先缩放到逻辑基准尺寸 256x256
            pix = pix.scaled(
                BASE_SIZE,
                BASE_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )   
            frames.append(pix)

        if frames:
            self.animations["idle"] = frames

    # -------------------------------------------------
    # playback core
    # -------------------------------------------------

    def _play_state(self, name: str, fps: int):
        frames = self.animations.get(name)
        if not frames:
            return

        if self.state == name and self.timer.isActive():
            return

        self.state = name
        self.frames = frames
        self.frame_index = 0

        interval = int(1000 / max(1, fps))
        self.timer.setInterval(interval)
        self.timer.start()

        # 立即显示第一帧，避免等待 timer
        self.target.setPixmap(self.frames[0])

    def _next_frame(self):
        if not self.frames:
            self.timer.stop()
            return

        self.frame_index = (self.frame_index + 1) % len(self.frames)
        self.target.setPixmap(self.frames[self.frame_index])

    # -------------------------------------------------
    # public hooks (PetWindow 调用的接口，保持不变)
    # -------------------------------------------------

    def on_idle(self):
        """待机动画（循环）"""
        self._play_state("idle", fps=2)

    def on_move(self, x: int, y: int):
        """
        拖动时的动画（暂时不实现，结构已预留）
        """
        pass

    def on_poke(self):
        """
        被戳一下的反馈（暂时仍使用抖动）
        """
        parent = self.target.parentWidget()
        if not parent:
            return

        orig = parent.geometry()
        offsets = [(4, 0), (-4, 0), (0, 4), (0, -4), (0, 0)]

        delay = 0
        for dx, dy in offsets:
            QTimer.singleShot(
                delay,
                lambda ox=dx, oy=dy, o=orig: parent.setGeometry(
                    o.x() + ox, o.y() + oy, o.width(), o.height()
                )
            )
            delay += 40
