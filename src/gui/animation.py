# src/gui/animation.py
from PySide6.QtCore import QTimer, QObject, Signal  # 新增 Signal 导入
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
import os
from utils import resource_path

BASE_SIZE = 256  # ⭐ 逻辑基准尺寸（与你原来的 pet.png 一致）
EMOJI_SIZE = 64  # 表情在基准尺寸下的固定大小（九宫格右上角：256/3≈85，取64更协调）

class AnimationDriver(QObject):
    """
    AnimationDriver
    - 管理所有动画帧
    - 只负责“怎么播”，不关心“什么时候播”
    """
    idle_frames_loaded = Signal()
    # 新增：表情加载完成信号
    emoji_loaded = Signal(QPixmap)

    def __init__(self, target_label):
        super().__init__()
        self.target = target_label
        self.emoji_label = None  # 表情显示的Label（后续从PetWindow传入）

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
        # 新增：预加载所有情绪表情
        self.emoji_cache: dict[str, QPixmap] = {}
        self._load_all_emojis()
        
        # 新增：表情显示定时器
        self.emoji_timer = QTimer(self)
        self.emoji_timer.setSingleShot(True)
        self.emoji_timer.timeout.connect(self.hide_emoji)

        # 新增：获取 idle 动画第一帧
    def get_idle_first_frame(self):
        """获取idle动画的第一帧（用于初始显示）"""
        idle_frames = self.animations.get("idle")
        if idle_frames and len(idle_frames) > 0:
            return idle_frames[0]
        return None

    def _load_all_emojis(self):
        """预加载所有情绪标签对应的表情图片"""
        emoji_dir = resource_path("assets/images/emoji")
        if not os.path.isdir(emoji_dir):
            print(f"[AnimationDriver] 表情目录不存在：{emoji_dir}")
            return

        # 情绪标签与图片文件名映射（假设文件名=标签名.png）
        emotion_tags = ["喜爱", "开心", "干杯", "疑问", "伤心", "无聊", "尴尬", "生气", "平常"]
        for tag in emotion_tags:
            # 处理特殊标签的文件名（如“无聊/瞌睡”替换为“无聊_瞌睡”）
            filename = tag.replace("/", "_") + ".png"
            emoji_path = resource_path(f"assets/images/emoji/{filename}")
            if not os.path.exists(emoji_path):
                print(f"[AnimationDriver] 表情文件缺失：{emoji_path}")
                continue

            # 加载并缩放到基准表情尺寸
            pix = QPixmap(emoji_path)
            if pix.isNull():
                continue
            # 缩放到基准尺寸（保持比例）
            pix = pix.scaled(
                EMOJI_SIZE, EMOJI_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.emoji_cache[tag] = pix
        print(f"[AnimationDriver] 已加载表情数量：{len(self.emoji_cache)}")

    def show_emoji(self, emotion_tag: str, duration_s: int):
        """显示指定情绪标签的表情，持续指定秒数后隐藏"""
        # 新增：如果是平常标签，直接返回不处理
        if emotion_tag == "平常":
            return
        if not self.emoji_label or emotion_tag not in self.emoji_cache:
            return
        # 获取基准尺寸的表情图片
        emoji_pix = self.emoji_cache[emotion_tag]
        if emoji_pix.isNull():
            return

        # 停止原有定时器
        if self.emoji_timer.isActive():
            self.emoji_timer.stop()

        # 显示表情
        self.emoji_label.setPixmap(emoji_pix)
        self.emoji_label.show()

        # 设置持续时间
        self.emoji_timer.setInterval(max(1, int(duration_s)) * 1000)
        self.emoji_timer.start()

    def hide_emoji(self):
        """隐藏表情"""
        if self.emoji_label:
            self.emoji_label.hide()
            self.emoji_label.setPixmap(QPixmap())
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
