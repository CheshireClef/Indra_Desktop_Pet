# src/gui/pet_window.py
from email.mime import text
import os
from PySide6.QtWidgets import QWidget, QLabel, QMenu, QVBoxLayout
from PySide6.QtGui import QPixmap, QGuiApplication  # ✅ 修正 QGuiApplication 导入
from PySide6.QtCore import Qt, QPoint, QTimer, Signal, QThread, QPropertyAnimation, QRect
# 新增：导入 BASE_SIZE
from gui.animation import BASE_SIZE
# ✅ 全局导入基础模块（避免循环导入的模块用延迟导入）
from vision.screen_observer import ScreenObserver
from vision.qwen_vision import QwenVisionClient  # 提前导入，避免方法内重复导入
from utils import resource_path


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
    - 可配置时长后淡出消失
    - 自动修正位置到屏幕内
    """

    def __init__(self, text: str, max_width: int, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Window |  # 替换 Qt.Tool
            Qt.WindowDoesNotAcceptFocus |  # 新增：无焦点
            Qt.BypassWindowManagerHint  # 新增：绕过窗口管理器特殊处理（可选，增强稳定性）
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

    def set_lifetime(self, seconds: int):
        """设置气泡显示时长（秒）"""
        self._life_timer.setInterval(seconds * 1000)

    def _clamp_to_screen(self):
        """修正位置，确保气泡完全显示在屏幕内"""
        geo: QRect = self.frameGeometry()
        screen = QGuiApplication.screenAt(geo.center())
        if not screen:
            screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()

        # 修正X坐标
        if geo.left() < avail.left():
            self.move(avail.left() + 10, geo.y())
        elif geo.right() > avail.right():
            self.move(avail.right() - geo.width() - 10, geo.y())

        # 修正Y坐标
        if geo.top() < avail.top():
            self.move(geo.x(), avail.top() + 10)
        elif geo.bottom() > avail.bottom():
            self.move(geo.x(), avail.bottom() - geo.height() - 10)

    def popup(self, x: int, y: int):
        self.move(x, y)
        # 修正位置到屏幕内
        self._clamp_to_screen()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._life_timer.start()


class PetWindow(QWidget):
    """Transparent frameless pet window that shows a PNG with alpha and supports drag/poke."""
    toggled_visibility = Signal(bool)

    # 修改：image_path 设为可选参数
    def __init__(self, settings_manager=None, icon_path: str = None, image_path: str = ""):
        super().__init__(None, Qt.Window)

        # ✅ 延迟导入易产生循环依赖的模块（放在 __init__ 开头）
        from .animation import AnimationDriver  # 相对导入，匹配项目结构
        from .chat_bubble import ChatBubble     # 相对导入
        from .settings_dialog import SettingsDialog  # 相对导入
        from llm.chat_manager import ChatManager     # 绝对导入

        # 核心修改：用 resource_path 处理传入的路径
        self.image_path = resource_path(image_path) if image_path else ""
        self.icon_path = resource_path(icon_path) if icon_path else ""
        self.settings = settings_manager
        self._context_menu: QMenu | None = None

        self.vision_client = None
        self._observe_worker: ScreenObserveWorker | None = None

        # ✅ 保存导入的类到实例属性，供其他方法调用
        self._AnimationDriver = AnimationDriver
        self._ChatManager = ChatManager
        self._ChatBubble = ChatBubble
        self._SettingsDialog = SettingsDialog

        self._setup_window()
        self._setup_animation()  # 优先初始化动画（加载idle帧）
        self._load_image()       # 再加载初始图（idle第一帧）
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
        try:
            self.observe_screen_and_comment()
        except Exception as e:
            print(f"[ScreenWatch] 定时截图异常：{e}")
            # 重置worker，避免后续定时器失效
            self._observe_worker = None

    # ---------------- Window ----------------
    def _setup_window(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Window |  # 替换 Qt.Tool，使用标准顶级窗口
            Qt.WindowDoesNotAcceptFocus  # 新增：避免窗口获取焦点（保留Qt.Tool的无焦点特性）
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # 新增：避免窗口激活时抢占焦点（保留Qt.Tool的轻量特性）
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self.label = QLabel(self)
        self.label.setAttribute(Qt.WA_TranslucentBackground, True)
        self.label.setScaledContents(True)

        self._drag_offset = QPoint()
        self._is_hidden = False

        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.hide()  # 新增：初始隐藏窗口，等动画加载完成后显示

    # ---------------- Image ----------------
    def _load_image(self):
        """修改：不再加载pet.png，改为加载idle第一帧或透明图"""
        # 从动画驱动获取idle第一帧
        idle_first_frame = self.animation.get_idle_first_frame()
        if idle_first_frame:
            pix = idle_first_frame
        else:
            # 无idle帧时显示透明占位图（尺寸与基准一致）
            pix = QPixmap(BASE_SIZE, BASE_SIZE)
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
        # ✅ 使用实例属性中的 AnimationDriver
        self.animation = self._AnimationDriver(self.label)
        # 连接信号：idle帧加载完成后显示窗口
        self.animation.idle_frames_loaded.connect(self.show)
        # 启动时立即播放idle动画，无需等待idle_timer
        self.animation.on_idle()
        # 保留idle_timer，用于后续空闲检测（防止动画中断后恢复）
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self._on_idle)
        self.idle_timer.start(7000)

    # ---------------- Chat ----------------
    def _setup_chat(self):
        persona_path = resource_path("src/llm/persona.txt")  # 替换原 os.path.join 方式
        # ✅ 使用实例属性中的 ChatManager
        self.chat_manager = self._ChatManager(self.settings, persona_path)
        # ✅ 使用实例属性中的 ChatBubble
        self.chat_bubble = self._ChatBubble()
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
        self.setWindowOpacity(1.0)  # 恢复透明度再隐藏，避免下次显示时透明
        self.hide()
        self._is_hidden = True
        self.toggled_visibility.emit(False)

    def show_window(self):
        self.show()
        self.raise_()  # 提升窗口层级，避免被遮挡
        self.setWindowOpacity(1.0)  # 强制恢复100%透明度
        self.label.repaint()  # 强制重绘立绘
        self._is_hidden = False
        self.toggled_visibility.emit(True)

    def toggle_visibility(self):
        # 优化：新增窗口是否真的在屏幕上的校验（针对新窗口标志）
        is_window_visible = self.isVisible() and self.isWindow() and not self.isMinimized()
        if self._is_hidden or not is_window_visible or (self.isVisible() and self.windowOpacity() <= 0.05):
            self.show_window()
        else:
            self.hide_window()
    # ---------------- Settings ----------------
    def open_settings_window(self):
        if not self.settings:
            return

        # ✅ 使用实例属性中的 SettingsDialog
        dlg = self._SettingsDialog(self.settings, parent=self)
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

        # 从设置中读取气泡显示时长
        duration_s = 10  # 默认10秒
        if self.settings:
            duration_s = self.settings.get("behavior", "temp_bubble_duration_s", default=10)
            try:
                duration_s = max(1, int(duration_s))  # 确保至少1秒
            except Exception:
                duration_s = 10
        bubble.set_lifetime(duration_s)

        bubble.adjustSize()
        bw = bubble.width()
        bh = bubble.height()

        x = pet_geo.center().x() - bw // 2
        y = pet_geo.top() - bh - 10

        bubble.popup(x, y)