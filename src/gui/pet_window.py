import os
from PySide6.QtWidgets import QWidget, QLabel, QMenu
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QPoint, QTimer, Signal

from .animation import AnimationDriver
from gui.settings_dialog import SettingsDialog

# 对话相关
from gui.chat_bubble import ChatBubble
from llm.chat_manager import ChatManager


class PetWindow(QWidget):
    """Transparent frameless pet window that shows a PNG with alpha and supports drag/poke."""
    toggled_visibility = Signal(bool)

    def __init__(self, image_path: str, settings_manager=None, icon_path: str = None):
        super().__init__(None, Qt.Window)
        self.image_path = image_path
        self.icon_path = icon_path
        self.settings = settings_manager
        self._context_menu: QMenu | None = None

        self._setup_window()
        self._load_image()
        self._setup_animation()
        self._setup_chat()

        # ⭐ 用于区分单击 / 双击
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._trigger_poke)

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

    def _show_chat_bubble(self):
        geo = self.geometry()
        x = geo.right() + 10
        y = geo.top()

        self.chat_bubble.move(x, y)
        self.chat_bubble.show()
        self.chat_bubble.raise_()
        self.chat_bubble.activateWindow()
        self.chat_bubble.input_edit.setFocus()

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
            # ⭐ 延迟触发戳一下，等待是否为双击
            self._click_timer.start(220)
            event.accept()
        else:
            event.ignore()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            # ⭐ 双击时取消戳一下
            if self._click_timer.isActive():
                self._click_timer.stop()

            self._show_chat_bubble()
            event.accept()

    def _trigger_poke(self):
        """真正的单击戳一下"""
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
                idle_s = int(
                    self.settings.get("behavior", "idle_interval_s", default=7)
                )
                self.idle_timer.setInterval(max(1, idle_s) * 1000)
            except Exception:
                pass

            try:
                menu = getattr(self, "_context_menu", None)
                if menu and hasattr(menu, "_actions_refs"):
                    sw_action = menu._actions_refs.get("screen_watch")
                    if sw_action:
                        enabled = bool(
                            self.settings.get(
                                "behavior",
                                "screen_watch_enabled",
                                default=False
                            )
                        )
                        sw_action.setText(
                            "屏幕监视：开启" if enabled else "屏幕监视：关闭"
                        )
            except Exception:
                pass

    def on_screen_watch_toggled(self, enabled: bool):
        try:
            if hasattr(self, "screen_watcher") and self.screen_watcher is not None:
                if enabled:
                    self.screen_watcher.start()
                else:
                    self.screen_watcher.stop()
        except Exception:
            pass
