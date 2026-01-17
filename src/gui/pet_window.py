# src/gui/pet_window.py
import os
from PySide6.QtWidgets import QWidget, QLabel, QMenu, QVBoxLayout
from PySide6.QtGui import QPixmap, QGuiApplication
from PySide6.QtCore import Qt, QPoint, QTimer, Signal, QThread, QPropertyAnimation, QRect
from sklearn.preprocessing import scale
from gui.animation import BASE_SIZE, EMOJI_SIZE
from vision.screen_observer import ScreenObserver
from vision.qwen_vision import QwenVisionClient
from utils import resource_path


class ScreenObserveWorker(QThread):
    finished = Signal(str, str)
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
            reply, emotion_tag = self.chat_manager.send_screen_observation_with_tag(description)
            if not reply.strip():
                raise Exception("未生成有效评论")

            self.finished.emit(reply, emotion_tag)  # 传递情绪标签
        except Exception as e:
            error_msg = f"屏幕观察出错：{str(e)}"
            print(f"[ScreenObserveWorker] {error_msg}")
            self.error.emit(error_msg)


class TempBubble(QWidget):
    """优化后的临时聊天气泡（修复重绘/内存泄漏）"""
    def __init__(self, text: str, target_width: int, target_height: int, parent=None):
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
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.label.setStyleSheet("""
            background: rgba(40, 40, 40, 210);
            color: white;
            padding: 6px;
            border-radius: 8px;
        """)
        # 锁定文本框核心区域宽高比 1:0.618（扣除布局边距）
        self.label.setFixedSize(target_width - 20, target_height - 16)
        layout.addWidget(self.label)
        # 气泡整体尺寸（包含边距 + 额外16px）
        self.setFixedSize(target_width, target_height)

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
        # 新增：初始化表情Label
        self._setup_emoji_label()
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

    def _setup_emoji_label(self):
        """初始化表情显示Label（九宫格右上角）"""
        self.emoji_label = QLabel(self)
        self.emoji_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.emoji_label.setAttribute(Qt.WA_TranslucentBackground, True)
        self.emoji_label.setScaledContents(True)
        self.emoji_label.hide()  # 默认隐藏

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

        # 调整表情Label位置（九宫格右上角）
        # 基准尺寸256x256 → 九宫格每个格子≈85x85，右上角格子的坐标：x=171, y=0（256-85=171）
        base_emoji_x = BASE_SIZE - EMOJI_SIZE  # 原始右上角X
        base_emoji_y = 0                      # 原始右上角Y
        # 计算缩放后的偏移量（30px按scale适配，避免缩放后偏移失真）
        offset_left = int(30 * scale)
        # 最终坐标：右上角X - 左移偏移量，Y不变
        emoji_x = int(base_emoji_x * scale) - offset_left
        emoji_y = int(base_emoji_y * scale)
        # 表情尺寸仍按scale缩放（保留原有逻辑）
        emoji_width = int(EMOJI_SIZE * scale)
        emoji_height = int(EMOJI_SIZE * scale)
        # 唯一一次设置位置（后续永不修改）
        self.emoji_label.setGeometry(emoji_x, emoji_y, emoji_width, emoji_height)

        screen = self.screen().availableGeometry()
        self.move(
            screen.right() - pix.width() - 30,
            screen.bottom() - pix.height() - 30
        )
        self.update()  # 确保图片显示完整

    # ---------------- 动画初始化 ----------------
    def _setup_animation(self):
        self.animation = self._AnimationDriver(self.label)
        # 绑定表情Label到动画驱动
        self.animation.emoji_label = self.emoji_label
        self.animation.idle_frames_loaded.connect(self._on_idle_frames_loaded)
        self.animation.on_idle()

        # 空闲检测定时器
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(lambda: (self.animation.on_idle(), self.update()))
        self.idle_timer.start(7000)
    
    # 新增：显示情绪表情的通用方法
    def _show_emotion_emoji(self, emotion_tag: str):
        """根据情绪标签显示表情，持续时间与临时气泡一致"""
        if emotion_tag == "平常":
            return
        # 获取临时气泡的显示时长
        duration_s = 10
        if self.settings:
            try:
                duration_s = int(self.settings.get("behavior", "temp_bubble_duration_s", default=10))
            except Exception:
                pass
        # 调用动画驱动的表情显示方法
        self.animation.show_emoji(emotion_tag, duration_s)

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
        # 调用修改后的chat方法，获取纯回复 + 情绪标签
        reply, emotion_tag = self.chat_manager.chat_with_tag(text)
        if reply:
            self.chat_bubble.append_pet(reply)
            # 显示对应情绪表情
            self._show_emotion_emoji(emotion_tag)

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
        self._observe_worker.finished.connect(lambda text, tag: (
            self.chat_bubble.append_pet_silent(text),
            self._show_temp_bubble(text),
            self._show_emotion_emoji(tag),  # 显示情绪表情
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
        # 初始最大宽度（文本框核心区域，未包含边距和额外16px）
        initial_max_width = int(pet_geo.width() * 1.8)
        min_width = 80  # 最小宽度限制，防止过窄
        golden_ratio = 0.618  # 强制锁定宽高比 1:0.618
        best_width = initial_max_width  # 默认初始最大宽度
        best_height = best_width * golden_ratio

        # 创建临时QLabel模拟文字排版，计算真实上边距
        temp_label = QLabel(text)
        temp_label.setWordWrap(True)
        temp_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        temp_label.setStyleSheet("""
            background: rgba(40, 40, 40, 210);
            color: white;
            padding: 8px;
            border-radius: 8px;
        """)
    
        # 核心修复：获取QFontMetrics对象（用于计算文本排版尺寸）
        fm = temp_label.fontMetrics()

        # 从大到小逐步缩小宽度，寻找满足条件的最佳尺寸
        for width in range(initial_max_width, min_width - 1, -1):
            height = width * golden_ratio
            temp_label.setFixedSize(width, height)
            # 修复：通过QFontMetrics计算文字实际排版的矩形区域
            text_rect = fm.boundingRect(
                QRect(0, 0, width, height),  # 文本框尺寸
                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap,  # 对齐+换行规则
                text  # 要计算的文本
            )
            # 计算文字上边距（文字顶部到label顶部的距离）
            top_margin = text_rect.top()
            # 满足核心条件：上边距 > 0 且 < 8px
            if 0 < top_margin < 8:
                best_width = width
                best_height = height
                break  # 找到第一个满足条件的宽度，停止遍历

        # 最终气泡尺寸：最佳宽高 + 16px（满足"宽度额外加16px"要求）
        final_width = int(best_width + 16)
        final_height = int(best_height + 16)

        # 创建自定义尺寸的气泡
        bubble = TempBubble(text, final_width, final_height, parent=self)
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