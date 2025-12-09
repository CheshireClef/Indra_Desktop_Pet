# src/gui/pet_window.py
import os
from PySide6.QtWidgets import QWidget, QLabel, QMenu
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QPoint, QTimer, Signal

from .animation import AnimationDriver
from gui.settings_dialog import SettingsDialog

class PetWindow(QWidget):
    """Transparent frameless pet window that shows a PNG with alpha and supports drag/poke."""
    toggled_visibility = Signal(bool)

    def __init__(self, image_path: str, settings_manager=None, icon_path: str = None):
        super().__init__(None, Qt.Window)
        self.image_path = image_path
        self.icon_path = icon_path
        self.settings = settings_manager  # 保存设置管理器
        self._context_menu: QMenu | None = None
        self._setup_window()
        self._load_image()   # 会使用 settings 中的 scale
        self._setup_animation()
        self._bind_flags()

    def _setup_window(self):
        # Frameless, always on top, translucent background
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Main label to display the pet pixmap
        self.label = QLabel(self)
        self.label.setAttribute(Qt.WA_TranslucentBackground, True)
        self.label.setScaledContents(True)

        # Drag helpers
        self._drag_offset = QPoint()
        self._is_hidden = False

        # Enable context menu policy so right-click triggers contextMenuEvent
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

    def _load_image(self):
        # load pixmap
        if not os.path.exists(self.image_path):
            pix = QPixmap(200, 300)
            pix.fill(Qt.transparent)
        else:
            pix = QPixmap(self.image_path)
            if pix.isNull():
                pix = QPixmap(200, 300)
                pix.fill(Qt.transparent)

        # apply scale from settings if available
        scale = 1.0
        try:
            if self.settings:
                scale = float(self.settings.get("pet", "scale", default=1.0))
        except Exception:
            scale = 1.0

# --- 新增：scale 合法范围保护 ---
        if scale <= 0 or scale > 5:   # 允许你根据需要设定最大值，比如 5 倍
            print(f"[Warning] Invalid scale={scale}, using default 1.0")
            scale = 1.0


        if scale != 1.0:
            w = int(pix.width() * scale)
            h = int(pix.height() * scale)
            pix = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self.label.setPixmap(pix)
        self.resize(pix.width(), pix.height())
        self.label.resize(pix.width(), pix.height())

        # reposition (optional)
        screen = self.screen().availableGeometry()
        x = screen.right() - pix.width() - 30
        y = screen.bottom() - pix.height() - 30
        self.move(x, y)

    def _setup_animation(self):
        self.animation = AnimationDriver(self.label)
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self._on_idle)
        self.idle_timer.start(7000)

    def _bind_flags(self):
        pass

    # ---------- Context menu handling ----------
    def set_context_menu(self, menu: QMenu):
        """
        设置右键菜单（传入由 AppTray.create_main_menu 创建并传入的同一份菜单）
        """
        self._context_menu = menu

    def contextMenuEvent(self, event):
        """
        当用户在立绘处右键时触发。我们显示同一份菜单实例（如果已设置）。
        """
        if self._context_menu:
            # 在鼠标位置显示（global pos）
            self._context_menu.exec(event.globalPos())
        else:
            # 没有设置菜单时，使用默认行为（或不显示）
            event.ignore()

    # ---------- Mouse events ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.RightButton:
            # 右键由 contextMenuEvent 处理（这里忽略）
            event.ignore()
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
            self.animation.on_poke()
            event.accept()
        else:
            event.ignore()

    def _on_idle(self):
        self.animation.on_idle()

    # ---------- Visibility helpers ----------
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

    def open_settings_window(self):
        if not self.settings:
            return
        dlg = SettingsDialog(self.settings, parent=self)
        if dlg.exec():
            # 用户点击保存，重新加载会受新配置影响
            self._load_image()
            # 如果你有 idle timer interval 等，也应该重设
            try:
                idle_s = int(self.settings.get("behavior", "idle_interval_s", default=7))
                self.idle_timer.setInterval(max(1, idle_s) * 1000)
            except Exception:
                pass