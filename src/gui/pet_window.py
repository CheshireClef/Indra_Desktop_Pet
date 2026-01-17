# src/gui/pet_window.py
import os
from PySide6.QtWidgets import QWidget, QLabel, QMenu, QVBoxLayout
from PySide6.QtGui import QPixmap, QGuiApplication
from PySide6.QtCore import Qt, QPoint, QTimer, Signal, QThread, QPropertyAnimation, QRect
from gui.animation import BASE_SIZE
from vision.screen_observer import ScreenObserver
from vision.qwen_vision import QwenVisionClient
from utils import resource_path


class ScreenObserveWorker(QThread):
    finished = Signal(str)
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
            reply = self.chat_manager.send_screen_observation(description)
            if not reply.strip():
                raise Exception("未生成有效评论")

            self.finished.emit(reply)
        except Exception as e:
            error_msg = f"屏幕观察出错：{str(e)}"
            print(f"[ScreenObserveWorker] {error_msg}")
            self.error.emit(error_msg)


class TempBubble(QWidget):
    """优化后的临时聊天气泡（修复重绘/内存泄漏）"""
    def __init__(self, text: str, max_width: int, parent=None):
        super().__init__(parent)

        # 优化窗口标志（跨平台兼容）
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Window |
            Qt.WindowDoesNotAcceptFocus |
            Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)  # 透明背景

        # 布局与样式
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.label.setStyleSheet("""
            background: rgba(40, 40, 40, 210);
            color: white;
            padding: 6px;
            border-radius: 8px;
        """)
        self.label.setMaximumWidth(max_width)
        layout.addWidget(self.label)
        self.adjustSize()

        # 淡出动画（优化销毁逻辑）
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(400)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self._on_fade_finished)

        self._life_timer = QTimer(self)
        self._life_timer.setSingleShot(True)
        self._life_timer.timeout.connect(self._fade_anim.start)

    def _on_fade_finished(self):
        """淡出后销毁，避免内存泄漏"""
        self.hide()
        self.deleteLater()

    def set_lifetime(self, seconds: int):
        self._life_timer.setInterval(max(1, int(seconds)) * 1000)

    def _clamp_to_screen(self):
        """修正位置，确保气泡在屏幕内"""
        geo = self.frameGeometry()
        screen = QGuiApplication.screenAt(geo.center()) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()

        # 修正坐标
        geo.moveLeft(max(avail.left() + 10, min(geo.left(), avail.right() - geo.width() - 10)))
        geo.moveTop(max(avail.top() + 10, min(geo.top(), avail.bottom() - geo.height() - 10)))
        self.setGeometry(geo)
        self.update()  # 触发重绘

    def popup(self, x: int, y: int):
        self.move(x, y)
        self._clamp_to_screen()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._life_timer.start()


class PetWindow(QWidget):
    toggled_visibility = Signal(bool)

    def __init__(self, settings_manager=None, icon_path: str = None, image_path: str = ""):
        super().__init__(None, Qt.Window)

        # 延迟导入避免循环依赖
        from .animation import AnimationDriver
        from .chat_bubble import ChatBubble
        from .settings_dialog import SettingsDialog
        from llm.chat_manager import ChatManager

        # 路径处理
        self.image_path = resource_path(image_path) if image_path else ""
        self.icon_path = resource_path(icon_path) if icon_path else ""
        self.settings = settings_manager
        self._context_menu = None

        # 截图用临时属性（主线程存储，避免跨线程访问）
        self._old_opacity = 1.0
        self._old_mouse_transparent = False

        self.vision_client = None
        self._observe_worker = None

        # 保存类引用
        self._AnimationDriver = AnimationDriver
        self._ChatManager = ChatManager
        self._ChatBubble = ChatBubble
        self._SettingsDialog = SettingsDialog

        # 初始化流程
        self._setup_window()
        self._setup_animation()
        self._load_image()
        self._setup_chat()
        self._setup_screen_watch()

        # 单击/双击区分
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._trigger_poke)

        # 屏幕观察器初始化
        self.screen_observer = ScreenObserver(self, self.settings)

    # ---------------- 新增：截图专用UI操作（主线程执行） ----------------
    def _hide_for_screenshot(self):
        """隐藏桌宠（主线程）"""
        self._old_opacity = self.windowOpacity()
        self._old_mouse_transparent = self.testAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWindowOpacity(0.0)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.update()  # 替代repaint，高效重绘

    def _restore_after_screenshot(self):
        """恢复桌宠（主线程）"""
        self.setWindowOpacity(self._old_opacity)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self._old_mouse_transparent)
        self.update()

    # ---------------- 屏幕观察定时器 ----------------
    def _setup_screen_watch(self):
        self.screen_watch_timer = QTimer(self)
        self.screen_watch_timer.timeout.connect(self._on_screen_watch_timeout)
        self._apply_screen_watch_settings()

    def _apply_screen_watch_settings(self):
        if not self.settings:
            return
        enabled = self.settings.get("behavior", "screen_watch_enabled", default=False)
        interval_s = self.settings.get("behavior", "screen_watch_interval_s", default=60)
        interval_ms = max(5, int(interval_s)) * 1000

        self.screen_watch_timer.stop()
        if enabled:
            self.screen_watch_timer.start(interval_ms)
            print(f"[ScreenWatch] 已启用，间隔 {interval_ms//1000}s")
        else:
            print("[ScreenWatch] 已关闭")

    def _on_screen_watch_timeout(self):
        if self._observe_worker and self._observe_worker.isRunning():
            return
        try:
            self.observe_screen_and_comment()
        except Exception as e:
            self._show_temp_bubble(f"定时屏幕观察出错：{str(e)}")
            self._observe_worker = None

    # ---------------- 窗口初始化 ----------------
    def _setup_window(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Window |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self.label = QLabel(self)
        self.label.setAttribute(Qt.WA_TranslucentBackground, True)
        self.label.setScaledContents(True)

        self._drag_offset = QPoint()
        self._is_hidden = False
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.hide()  # 初始隐藏，等动画加载

    # ---------------- 图片加载 ----------------
    def _load_image(self):
        """加载动画帧或透明占位图"""
        idle_first_frame = self.animation.get_idle_first_frame()
        pix = idle_first_frame if idle_first_frame else QPixmap(BASE_SIZE, BASE_SIZE)
        if not idle_first_frame:
            pix.fill(Qt.transparent)

        # 缩放处理
        scale = 1.0
        if self.settings:
            try:
                scale = max(0.1, min(5.0, float(self.settings.get("pet", "scale", default=1.0))))
            except Exception:
                scale = 1.0

        if scale != 1.0:
            pix = pix.scaled(
                int(pix.width()*scale), int(pix.height()*scale),
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )

        # 应用图片并调整位置
        self.label.setPixmap(pix)
        self.resize(pix.size())
        self.label.resize(pix.size())

        screen = self.screen().availableGeometry()
        self.move(
            screen.right() - pix.width() - 30,
            screen.bottom() - pix.height() - 30
        )
        self.update()  # 确保图片显示完整

    # ---------------- 动画初始化 ----------------
    def _setup_animation(self):
        self.animation = self._AnimationDriver(self.label)
        self.animation.idle_frames_loaded.connect(self._on_idle_frames_loaded)
        self.animation.on_idle()

        # 空闲检测定时器
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(lambda: (self.animation.on_idle(), self.update()))
        self.idle_timer.start(7000)

    def _on_idle_frames_loaded(self):
        """动画帧加载完成后显示窗口并重绘"""
        self.show()
        self.raise_()
        self.update()

    # ---------------- 聊天功能 ----------------
    def _setup_chat(self):
        persona_path = resource_path("src/llm/persona.txt")
        self.chat_manager = self._ChatManager(self.settings, persona_path)
        self.chat_bubble = self._ChatBubble()
        self.chat_bubble.send_message.connect(self._on_user_message)

    def _on_user_message(self, text: str):
        reply = self.chat_manager.chat(text)
        if reply:
            self.chat_bubble.append_pet(reply)

    # ---------------- 右键菜单 ----------------
    def set_context_menu(self, menu):
        self._context_menu = menu

    def contextMenuEvent(self, event):
        if self._context_menu:
            self._context_menu.exec(event.globalPos())
        else:
            event.ignore()

    # ---------------- 鼠标事件 ----------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            geom = self.screen().availableGeometry()
            new_x = max(0, min(new_pos.x(), geom.width() - self.width()))
            new_y = max(0, min(new_pos.y(), geom.height() - self.height()))
            self.move(new_x, new_y)
            self.animation.on_move(new_x, new_y)
            self.update()  # 移动后重绘
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._click_timer.start(220)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self._click_timer.isActive():
            self._click_timer.stop()
            self.chat_bubble.show()
            event.accept()

    def _trigger_poke(self):
        self.animation.on_poke()
        self.update()

    # ---------------- 可见性控制 ----------------
    def hide_window(self):
        self.setWindowOpacity(1.0)
        self.hide()
        self._is_hidden = True
        self.toggled_visibility.emit(False)
        self.update()

    def show_window(self):
        self.show()
        self.raise_()
        self.setWindowOpacity(1.0)
        self.label.repaint()  # 强制重绘立绘，避免空白
        self._is_hidden = False
        self.toggled_visibility.emit(True)
        self.update()

    def toggle_visibility(self):
        is_visible = self.isVisible() and self.isWindow() and not self.isMinimized()
        if self._is_hidden or not is_visible or self.windowOpacity() <= 0.05:
            self.show_window()
        else:
            self.hide_window()

    # ---------------- 设置窗口 ----------------
    def open_settings_window(self):
        if not self.settings:
            return
        dlg = self._SettingsDialog(self.settings, parent=self)
        if dlg.exec():
            self._load_image()
            try:
                idle_s = int(self.settings.get("behavior", "idle_interval_s", default=7))
                self.idle_timer.setInterval(max(1, idle_s) * 1000)
            except Exception:
                pass
            self._apply_screen_watch_settings()
            self.update()

    # ---------------- 视觉功能 ----------------
    def _ensure_vision_client(self):
        if self.vision_client or not self.settings:
            return
        api_url = self.settings.get("vision", "api_url", default="https://api.siliconflow.cn/v1/chat/completions")
        api_key = self.settings.get("vision", "api_key", default="")
        model = self.settings.get("vision", "model", default="Qwen/Qwen3-VL-32B-Instruct")

        if not api_key:
            print("[Vision] API密钥为空，视觉功能禁用")
            return
        self.vision_client = QwenVisionClient(api_url=api_url, api_key=api_key, model=model)

    def observe_screen_and_comment(self):
        self._ensure_vision_client()
        if not self.vision_client:
            self._show_temp_bubble("屏幕观察功能未启用：未配置有效的视觉模型API密钥")
            return
        if self._observe_worker and self._observe_worker.isRunning():
            self._show_temp_bubble("屏幕观察正在进行中，请稍候")
            return

        self._observe_worker = ScreenObserveWorker(self.screen_observer, self.vision_client, self.chat_manager)
        self._observe_worker.finished.connect(lambda text: (
            self.chat_bubble.append_pet_silent(text),
            self._show_temp_bubble(text),
            setattr(self, "_observe_worker", None)
        ))
        self._observe_worker.error.connect(lambda msg: (
            self._show_temp_bubble(msg),
            setattr(self, "_observe_worker", None)
        ))
        self._observe_worker.start()

    # ---------------- 临时气泡显示 ----------------
    def _show_temp_bubble(self, text: str):
        # 错误信息标红
        if text.startswith(("屏幕观察出错：", "定时屏幕观察出错：", "屏幕观察功能未启用：")):
            text = f"<font color='#ff4444'>{text}</font>"

        pet_geo = self.geometry()
        max_width = int(pet_geo.width() * 1.8)
        bubble = TempBubble(text, max_width, parent=self)

        # 读取显示时长
        duration_s = 10
        if self.settings:
            try:
                duration_s = int(self.settings.get("behavior", "temp_bubble_duration_s", default=10))
            except Exception:
                pass

        bubble.set_lifetime(duration_s)
        bubble.adjustSize()
        # 气泡位置：桌宠头顶居中
        x = pet_geo.center().x() - bubble.width() // 2
        y = pet_geo.top() - bubble.height() - 10
        bubble.popup(x, y)