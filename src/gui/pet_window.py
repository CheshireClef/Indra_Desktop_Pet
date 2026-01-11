# src/gui/pet_window.py
from email.mime import text
import os
from PySide6.QtWidgets import QWidget, QLabel, QMenu, QVBoxLayout
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QPoint, QTimer, Signal, QThread, QPropertyAnimation

from .animation import AnimationDriver
from gui.settings_dialog import SettingsDialog
from gui.chat_bubble import ChatBubble
from llm.chat_manager import ChatManager


class ScreenObserveWorker(QThread):
    finished = Signal(str)

    def __init__(self, observer, vision_client, chat_manager):
        super().__init__()
        self.observer = observer
        self.vision_client = vision_client
        self.chat_manager = chat_manager

    def run(self):
        try:
            screenshot_path = self.observer.observe_once()
            description = self.vision_client.describe_image(screenshot_path)
            reply = self.chat_manager.send_screen_observation(description)
            if reply:
                self.finished.emit(reply)
        except Exception as e:
            print("[ScreenObserveWorker] error:", e)


class TempBubble(QWidget):
    """
    一次性临时聊天气泡
    - 不抢焦点
    - 自动大小
    - 10 秒后淡出消失
    """

    def __init__(self, text: str, max_width: int, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.Tool |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.label.setStyleSheet(
            """
            background: rgba(40, 40, 40, 210);
            color: white;
            padding: 6px;
            """
        )

        self.label.setMaximumWidth(max_width)
        layout.addWidget(self.label)

        self.adjustSize()

        # --- 自动淡出 ---
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(400)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self.hide)

        self._life_timer = QTimer(self)
        self._life_timer.setSingleShot(True)
        self._life_timer.timeout.connect(self._fade_anim.start)

    def popup(self, x: int, y: int):
        self.move(x, y)
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self.activateWindow()
        self._life_timer.start(10000)


class PetWindow(QWidget):
    """Transparent frameless pet window that shows a PNG with alpha and supports drag/poke."""
    toggled_visibility = Signal(bool)

    def __init__(self, image_path: str, settings_manager=None, icon_path: str = None):
        from vision.screen_observer import ScreenObserver
        super().__init__(None, Qt.Window)

        self.image_path = image_path
        self.icon_path = icon_path
        self.settings = settings_manager
        self._context_menu: QMenu | None = None

        self.vision_client = None
        self._observe_worker: ScreenObserveWorker | None = None

        self._setup_window()
        self._load_image()
        self._setup_animation()
        self._setup_chat()
        # ---------- 主动屏幕观察 Timer ----------
        self.screen_watch_timer = QTimer(self)
        self.screen_watch_timer.timeout.connect(
        self._on_screen_watch_timeout
       )
        self._apply_screen_watch_settings()


        # ⭐ 用于区分单击 / 双击
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._trigger_poke)

        self.screen_observer = ScreenObserver(self, self.settings)

    # ---------------- Vision ----------------
    def _ensure_vision_client(self):
        if self.vision_client or not self.settings:
            return

        from vision.qwen_vision import QwenVisionClient

        api_url = self.settings.get(
            "vision", "api_url",
            default="https://api.siliconflow.cn/v1/chat/completions"
        )
        api_key = self.settings.get("vision", "api_key", default="")
        model = self.settings.get(
            "vision", "model",
            default="Qwen/Qwen3-VL-32B-Instruct"
        )

        if not api_key:
            print("[Vision] API key is empty, vision disabled")
            return

        self.vision_client = QwenVisionClient(
            api_url=api_url,
            api_key=api_key,
            model=model
        )

    def _apply_screen_watch_settings(self):
        """
        根据 settings 启动 / 停止 主动屏幕观察
        """
        if not self.settings:
            return

        enabled = self.settings.get(
            "behavior",
            "screen_watch_enabled",
            default=False
        )   
        interval_s = self.settings.get(
            "behavior",
            "screen_watch_interval_s",
            default=60
        )
        try:
            interval_ms = max(5, int(interval_s)) * 1000
        except Exception:
            interval_ms = 60000

        self.screen_watch_timer.stop()

        if enabled:
            self.screen_watch_timer.start(interval_ms)
            print(f"[ScreenWatch] 已启用，间隔 {interval_ms // 1000}s")
        else:
            print("[ScreenWatch] 已关闭")
   
    def _on_screen_watch_timeout(self):
        """
        定时主动观察屏幕
        """
        # 避免叠加线程
        if self._observe_worker and self._observe_worker.isRunning():
            return

        self.observe_screen_and_comment()

    # ---------------- Window ----------------
    def _setup_window(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.label = QLabel(self)
        self.label.setAttribute(Qt.WA_TranslucentBackground, True)
        self.label.setScaledContents(True)

        self._drag_offset = QPoint()
        self._is_hidden = False

        self.setContextMenuPolicy(Qt.DefaultContextMenu)

    # ---------------- Image ----------------
    def _load_image(self):
        if not os.path.exists(self.image_path):
            pix = QPixmap(200, 300)
            pix.fill(Qt.transparent)
        else:
            pix = QPixmap(self.image_path)
            if pix.isNull():
                pix = QPixmap(200, 300)
                pix.fill(Qt.transparent)

        scale = 1.0
        try:
            if self.settings:
                scale = float(self.settings.get("pet", "scale", default=1.0))
        except Exception:
            scale = 1.0

        if scale <= 0 or scale > 5:
            scale = 1.0

        if scale != 1.0:
            w = int(pix.width() * scale)
            h = int(pix.height() * scale)
            pix = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self.label.setPixmap(pix)
        self.resize(pix.width(), pix.height())
        self.label.resize(pix.width(), pix.height())

        screen = self.screen().availableGeometry()
        x = screen.right() - pix.width() - 30
        y = screen.bottom() - pix.height() - 30
        self.move(x, y)

    # ---------------- Animation ----------------
    def _setup_animation(self):
        self.animation = AnimationDriver(self.label)
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self._on_idle)
        self.idle_timer.start(7000)

    # ---------------- Chat ----------------
    def _setup_chat(self):
        persona_path = os.path.join("src", "llm", "persona.txt")
        self.chat_manager = ChatManager(self.settings, persona_path)

        self.chat_bubble = ChatBubble()
        self.chat_bubble.send_message.connect(self._on_user_message)

    def _on_user_message(self, text: str):
        reply = self.chat_manager.chat(text)
        if reply:
            self.chat_bubble.append_pet(reply)

    # ---------------- Context Menu ----------------
    def set_context_menu(self, menu):
        self._context_menu = menu

    def contextMenuEvent(self, event):
        if self._context_menu:
            self._context_menu.exec(event.globalPos())
        else:
            event.ignore()

    # ---------------- Mouse ----------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self.frameGeometry().topLeft()
            )
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            geom = self.screen().availableGeometry()
            w, h = self.width(), self.height()
            new_x = max(0, min(new_pos.x(), geom.width() - w))
            new_y = max(0, min(new_pos.y(), geom.height() - h))
            self.move(new_x, new_y)
            self.animation.on_move(new_x, new_y)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._click_timer.start(220)
            event.accept()
        else:
            event.ignore()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._click_timer.isActive():
                self._click_timer.stop()
            self.chat_bubble.show()
            event.accept()

    def _trigger_poke(self):
        self.animation.on_poke()

    # ---------------- Idle ----------------
    def _on_idle(self):
        self.animation.on_idle()

    # ---------------- Visibility ----------------
    def hide_window(self):
        self.hide()
        self._is_hidden = True
        self.toggled_visibility.emit(False)

    def show_window(self):
        self.show()
        self._is_hidden = False
        self.toggled_visibility.emit(True)

    def toggle_visibility(self):
        if self._is_hidden:
            self.show_window()
        else:
            self.hide_window()

    # ---------------- Settings ----------------
    def open_settings_window(self):
        if not self.settings:
            return

        dlg = SettingsDialog(self.settings, parent=self)
        if dlg.exec():
            self._load_image()
            try:
                idle_s = int(self.settings.get("behavior", "idle_interval_s", default=7))
                self.idle_timer.setInterval(max(1, idle_s) * 1000)
            except Exception:
                pass
            self._apply_screen_watch_settings()

    # ---------------- Vision Action ----------------
    def observe_screen_and_comment(self):
        self._ensure_vision_client()
        if not self.vision_client:
            return

        if self._observe_worker and self._observe_worker.isRunning():
            return

        self._observe_worker = ScreenObserveWorker(
            self.screen_observer,
            self.vision_client,
            self.chat_manager
        )

        def on_screen_observed(text: str):
            # 1️⃣ 只追加到聊天记录（不显示聊天框）
            self.chat_bubble.append_pet_silent(text)

            # 2️⃣ 显示头顶临时气泡
            self._show_temp_bubble(text)

        self._observe_worker.finished.connect(on_screen_observed)
        self._observe_worker.start()


    
    # ---------------- 临时气泡 ----------------
    def _show_temp_bubble(self, text: str):
        pet_geo = self.geometry()
        pet_width = pet_geo.width()

        max_width = int(pet_width * 1.8)

        bubble = TempBubble(text, max_width, parent=self)

        bubble.adjustSize()
        bw = bubble.width()
        bh = bubble.height()

        x = pet_geo.center().x() - bw // 2
        y = pet_geo.top() - bh - 10

        bubble.popup(x, y)
