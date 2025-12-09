# src/gui/animation.py
from PySide6.QtCore import QTimer, QObject
from PySide6.QtGui import QPixmap
import os

class AnimationDriver(QObject):
    """
    AnimationDriver is the single place to implement/replace animation logic.
    - on_idle: called periodically for idle animations (blink, sway)
    - on_move: called while dragging/moving (can trigger a "walking" animation)
    - on_poke: called when user clicks/pokes the pet (play a poke animation)
    
    Implementation notes:
    - For frame-based animations, keep frames list of QPixmaps and a QTimer to step frames.
    - For smooth transforms, you can use QPropertyAnimation on the widget geometry or opacity.
    """
    def __init__(self, target_label):
        super().__init__()
        self.target = target_label
        self.frames = []          # list[QPixmap]
        self.frame_index = 0
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self._next_frame)
        self.playing = False

        # Placeholder: you can fill self.frames from a directory when you have assets
        # Example: self.load_frames("assets/anim/idle")
        self._load_placeholder()

    def _load_placeholder(self):
        # if no frames, we keep the single pixmap already set on target
        pass

    def load_frames(self, folder_path: str):
        """Load all png frames in folder_path into self.frames (ordered)."""
        if not os.path.isdir(folder_path):
            return
        files = sorted(f for f in os.listdir(folder_path) if f.lower().endswith((".png", ".jpg", ".webp")))
        self.frames = []
        for f in files:
            pix = QPixmap(os.path.join(folder_path, f))
            if not pix.isNull():
                self.frames.append(pix)

    def _next_frame(self):
        if not self.frames:
            self.stop()
            return
        self.frame_index = (self.frame_index + 1) % len(self.frames)
        self.target.setPixmap(self.frames[self.frame_index])

    def play(self, fps=12):
        if not self.frames:
            return
        self.timer.setInterval(int(1000 / max(1, fps)))
        self.playing = True
        self.timer.start()

    def stop(self):
        if self.timer.isActive():
            self.timer.stop()
        self.playing = False

    # ---------- public hooks ----------
    def on_idle(self):
        """
        Called periodically to perform idle animations. By default we'll try to blink
        if idle frames available.
        """
        # simple example: play idle frames folder if exists
        if self.frames:
            self.play(fps=8)
            # set a timer to stop after one cycle (optional)
            QTimer.singleShot(800, self.stop)

    def on_move(self, x: int, y: int):
        """
        Called when the pet is being dragged/moved. Could switch to a 'dragging' frame or play
        a subtle effect. Default: do nothing.
        """
        # Implement later: load drag frames and play them
        pass

    def on_poke(self):
        """
        Called when user pokes (clicks). Implement a short animation:
        - small shake: translate widget (handled at PetWindow or via QPropertyAnimation)
        - or play poke frames
        """
        # default behavior: small visual shake via geometry change on target's parent
        parent = self.target.parentWidget()
        if not parent:
            return
        orig = parent.geometry()
        offsets = [(4,0),(-4,0),(0,4),(0,-4),(0,0)]
        # simple non-blocking sequence via singleShot
        delay = 0
        for dx, dy in offsets:
            QTimer.singleShot(delay, lambda ox=dx, oy=dy, orect=orig: parent.setGeometry(
                orect.x()+ox, orect.y()+oy, orect.width(), orect.height()))
            delay += 40
# 如何接入你的帧资源（后期）

# 放帧序列到 assets/anim/idle/（按文件名排序），并在启动或切换状态时调用 animation.load_frames("assets/anim/idle") 然后 animation.play()。

# 或者用 gif：QMovie 直接赋给 QLabel（可参考官方 QMovie API）。