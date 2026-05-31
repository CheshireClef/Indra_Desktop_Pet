# src/gui/animation.py
"""
动画驱动模块
负责加载和管理桌宠的帧动画 (Frame Animation) 和表情图标 (Emoji)。
"""
from PySide6.QtCore import QTimer, QObject, Signal  # 新增 Signal 导入
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
import os
import time
from utils import resource_path, ResourceManager

BASE_SIZE = 256  # ⭐ 逻辑基准尺寸（与你原来的 pet.png 一致）
EMOJI_SIZE = 64  # 表情在基准尺寸下的固定大小（九宫格右上角：256/3≈85，取64更协调）

class AnimationDriver(QObject):
    """
    AnimationDriver
    - 管理所有动画帧 (Frames)
    - 管理表情资源 (Emojis)
    - 负责定时触发下一帧信号，不直接操作 UI 组件，只发送信号
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

        # 启动：仅加载首帧，其余 idle 帧与表情延后；由 PetWindow 连接信号后再触发显示
        self._load_boot_frame()
        QTimer.singleShot(0, self._deferred_load_assets)
        
        # 新增：表情显示定时器
        self.emoji_timer = QTimer(self)
        self.emoji_timer.setSingleShot(True)
        self.emoji_timer.timeout.connect(self.hide_emoji)

    def _load_boot_frame(self):
        """启动阶段只加载 idle 第一帧（或 pet.png），尽快结束阻塞。"""
        self.emoji_cache: dict[str, QPixmap] = {}
        folder = resource_path("assets/images/idle")
        frames: list[QPixmap] = []
        if os.path.isdir(folder):
            files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
            if files:
                pix = ResourceManager.get_instance().get_image(
                    f"assets/images/idle/{files[0]}"
                )
                if not pix.isNull():
                    pix = pix.scaled(
                        BASE_SIZE,
                        BASE_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    frames.append(pix)
        if not frames:
            pix = ResourceManager.get_instance().get_image("assets/images/pet.png")
            if not pix.isNull():
                pix = pix.scaled(
                    BASE_SIZE,
                    BASE_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                frames.append(pix)
        if frames:
            self.animations["idle"] = frames

    def _deferred_load_assets(self):
        """事件循环开始后加载完整 idle 动画与表情（不阻塞 splash）。"""
        t0 = time.perf_counter()
        self._load_idle_frames()
        self._load_all_emojis()
        if self.state == "idle" and self.animations.get("idle"):
            self.frames = self.animations["idle"]
            self.frame_index = 0
            if self.frames:
                self.target.setPixmap(self.frames[0])
        print(
            f"[AnimationDriver] 延后资源加载完成 {time.perf_counter() - t0:.2f}s "
            f"(idle={len(self.animations.get('idle', []))} 帧)"
        )
    def get_idle_first_frame(self):
        """获取idle动画的第一帧（用于初始显示）"""
        idle_frames = self.animations.get("idle")
        if idle_frames and len(idle_frames) > 0:
            return idle_frames[0]
        return None

    def _load_all_emojis(self):
        """预加载所有情绪标签对应的表情图片，并缩放到标准尺寸"""
        emoji_dir = resource_path("assets/images/emoji")
        if not os.path.isdir(emoji_dir):
            print(f"[AnimationDriver] 表情目录不存在：{emoji_dir}")
            return

        # 情绪标签与图片文件名映射（假设文件名=标签名.png）
        emotion_tags = ["喜爱", "开心", "干杯", "疑问", "伤心", "无聊", "尴尬", "生气"]
        for tag in emotion_tags:
            # 处理特殊标签的文件名（如“无聊/瞌睡”替换为“无聊_瞌睡”）
            filename = tag.replace("/", "_") + ".png"
            
            # 使用 ResourceManager 加载
            pix = ResourceManager.get_instance().get_image(f"assets/images/emoji/{filename}")
            
            if pix.isNull():
                # ResourceManager 已处理文件不存在的情况，返回空 pixmap
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
            # 使用 ResourceManager 加载
            pix = ResourceManager.get_instance().get_image(f"assets/images/idle/{f}")
            
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
