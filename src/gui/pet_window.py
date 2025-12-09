# src/gui/pet_window.py
import os
from PySide6.QtWidgets import QWidget, QLabel, QMenu
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QPoint, QTimer, Signal

from .animation import AnimationDriver

class PetWindow(QWidget):
    """Transparent frameless pet window that shows a PNG with alpha and supports drag/poke."""
    toggled_visibility = Signal(bool)
# 缩放参数scale=1.0
    def __init__(self, image_path: str, icon_path: str = None, scale: float = 0.8):
        super().__init__(None, Qt.Window)
        self.image_path = image_path
        self.icon_path = icon_path
        self._context_menu: QMenu | None = None  # 将被 set_context_menu 填入
        self._setup_window()
        self._load_image()
        self._setup_animation()
        self._bind_flags()
        self.scale = scale

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
        # Load pixmap from file; if missing show default size
        if not os.path.exists(self.image_path):
            print(f"[PetWindow] image not found: {self.image_path}")
            pix = QPixmap(200, 300)
            pix.fill(Qt.transparent)
        else:
            pix = QPixmap(self.image_path)
            if pix.isNull():
                print("[PetWindow] failed to load image (pixmap null)")
                pix = QPixmap(200, 300)
                pix.fill(Qt.transparent)
        # --- 统一缩放 ---
        if self.scale != 1.0:
            w = int(pix.width() * self.scale)
            h = int(pix.height() * self.scale)
            pix = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self.label.setPixmap(pix)
        self.resize(pix.width(), pix.height())
        self.label.resize(pix.width(), pix.height())

        # place near bottom-right by default
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
