# src/gui/pet_window.py
"""
主窗口模块
定义了 PetWindow 类，即桌宠的实体窗口。
包含窗口初始化、动画驱动、交互事件处理 (点击、拖拽)、以及与其他模块 (聊天、设置、视觉) 的集成。
"""
import os
from PySide6.QtWidgets import QWidget, QLabel, QMenu, QVBoxLayout
from PySide6.QtGui import QPixmap, QGuiApplication
from PySide6.QtCore import Qt, QPoint, QTimer, Signal, QThread, QPropertyAnimation, QRect, QSize
from gui.animation import BASE_SIZE, EMOJI_SIZE
from utils import resource_path
from .chat_bubble import TempBubble
from workers.screen_observer_worker import ScreenObserveWorker


class PetWindow(QWidget):
    """
    桌宠主窗口类
    继承自 QWidget，设置为无边框、透明背景、置顶显示。
    """
    # 窗口可见性切换信号
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
        
        # 优化：使用单例模式获取 SettingsManager（如果未传入）
        if settings_manager:
            self.settings = settings_manager
        else:
            from settings_manager import SettingsManager
            self.settings = SettingsManager.get_instance()

        if self.settings:
            # 绑定配置变更信号，实现实时刷新
            self.settings.settings_changed.connect(self._on_settings_changed)

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
        self._load_image(reset_pos=True)

        # 优化启动速度：延迟初始化重型组件
        QTimer.singleShot(200, self._setup_chat)
        QTimer.singleShot(500, self._setup_screen_watch)

        # 单击/双击区分
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._trigger_poke)

        # 屏幕观察器延迟初始化，此处仅占位
        self.screen_observer = None
        
        # 记录当前显示的临时气泡，用于防止重叠
        self.current_temp_bubble = None

        # 缩放设置防抖定时器
        self._save_settings_timer = QTimer(self)
        self._save_settings_timer.setSingleShot(True)
        self._save_settings_timer.timeout.connect(lambda: self.settings.save() if self.settings else None)

    def _setup_emoji_label(self):
        """初始化表情显示Label（九宫格右上角）"""
        self.emoji_label = QLabel(self)
        # 鼠标穿透：确保表情不会阻挡对宠物的点击
        self.emoji_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.emoji_label.setAttribute(Qt.WA_TranslucentBackground, True)
        self.emoji_label.setScaledContents(True)
        self.emoji_label.hide()  # 默认隐藏

    # ---------------- 新增：截图专用UI操作（主线程执行） ----------------
    def _hide_for_screenshot(self):
        """隐藏桌宠（主线程），用于在截图前将自己隐身"""
        self._old_opacity = self.windowOpacity()
        self._old_mouse_transparent = self.testAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWindowOpacity(0.0)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.update()  # 替代repaint，高效重绘

    def _restore_after_screenshot(self):
        """恢复桌宠（主线程），截图完成后现身"""
        self.setWindowOpacity(self._old_opacity)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self._old_mouse_transparent)
        self.update()

    # ---------------- 屏幕观察定时器 ----------------
    def _setup_screen_watch(self):
        # 懒加载 ScreenObserver
        if self.screen_observer is None:
            from vision.screen_observer import ScreenObserver
            self.screen_observer = ScreenObserver(self, self.settings)

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
    def _load_image(self, reset_pos=False):
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

        if reset_pos:
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
        
        # 绑定知识库加载完成信号
        if hasattr(self.chat_manager, 'knowledge_base'):
            self.chat_manager.knowledge_base.indices_loaded.connect(self._on_indices_loaded)
            self.chat_manager.knowledge_base.model_loaded_to_cpu.connect(self._on_model_loaded_to_cpu)

        self.chat_bubble = self._ChatBubble()
        self.chat_bubble.send_message.connect(self._on_user_message)

    def _on_model_loaded_to_cpu(self):
        """模型加载到CPU后的回调"""
        print("[PetWindow] 收到模型加载完成信号")
        self._show_temp_bubble("数据库加载中，请稍候...加载期间可以进行无数据库支持的简单聊天")

    def _on_indices_loaded(self):
        """知识库索引加载完成后的回调"""
        print("[PetWindow] 收到索引加载完成信号")
        self._show_temp_bubble("数据库加载完成")

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

    # ---------------- 鼠标滚轮缩放 ----------------
    def wheelEvent(self, event):
        """鼠标滚轮事件：调整缩放比例"""
        # 计算缩放增量
        delta = event.angleDelta().y()
        if delta == 0:
            return
            
        current_scale = 1.0
        if self.settings:
            try:
                current_scale = float(self.settings.get("pet", "scale", default=1.0))
            except Exception:
                current_scale = 1.0
            
        # 滚轮向上(delta > 0) -> 放大，向下 -> 缩小
        step = 0.1
        if delta > 0:
            new_scale = current_scale + step
        else:
            new_scale = current_scale - step
            
        # 限制范围 (0.5 - 3.0)
        new_scale = max(0.5, min(3.0, new_scale))
        
        # 保留两位小数，避免精度问题
        new_scale = round(new_scale, 2)
        
        if new_scale != current_scale:
            # 1. 更新UI尺寸
            self._update_ui_size(new_scale)
            
            # 2. 更新设置（不立即保存，防止频繁IO）
            if self.settings:
                self.settings.set("pet", "scale", value=new_scale, save_now=False)
                # 重置防抖定时器 (1秒后保存)
                self._save_settings_timer.start(1000)
                
            # 3. 显示临时气泡提示当前比例
            self._show_temp_bubble(f"缩放比例: {int(new_scale * 100)}%")
            
        event.accept()

    def _update_ui_size(self, scale: float):
        """根据缩放比例更新窗口和控件尺寸"""
        # 1. 更新窗口和 Label 尺寸
        # 使用 BASE_SIZE 计算目标尺寸
        new_width = int(BASE_SIZE * scale)
        new_height = int(BASE_SIZE * scale)
        new_size = QSize(new_width, new_height)
        
        self.resize(new_size)
        self.label.resize(new_size)
        
        # 2. 更新表情 Label 位置和尺寸
        # 计算逻辑需与 _load_image 保持一致
        base_emoji_x = BASE_SIZE - EMOJI_SIZE
        base_emoji_y = 0
        offset_left = int(30 * scale)
        
        emoji_x = int(base_emoji_x * scale) - offset_left
        emoji_y = int(base_emoji_y * scale)
        emoji_width = int(EMOJI_SIZE * scale)
        emoji_height = int(EMOJI_SIZE * scale)
        
        self.emoji_label.setGeometry(emoji_x, emoji_y, emoji_width, emoji_height)
        # 触发重绘
        self.update()

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

    def _on_settings_changed(self):
        """配置变更时的自动刷新逻辑"""
        print("[PetWindow] 检测到配置变更，正在刷新...")
        
        # 1. 刷新外观（缩放/图片），不重置位置
        self._load_image(reset_pos=False)
        
        # 2. 刷新定时器间隔
        try:
            idle_s = int(self.settings.get("behavior", "idle_interval_s", default=7))
            current_interval = self.idle_timer.interval()
            new_interval = max(1, idle_s) * 1000
            if current_interval != new_interval:
                self.idle_timer.setInterval(new_interval)
        except Exception:
            pass
            
        # 3. 刷新屏幕观察设置
        self._apply_screen_watch_settings()
        
        # 4. 刷新视觉模型配置（如果在运行时修改了API Key）
        if self.vision_client:
             # 如果需要支持热更新 Vision Client，可以在这里重新初始化
             # 目前暂且保留现有实例，下次调用 _ensure_vision_client 时若为None会重建
             pass
             
        self.update()

    # ---------------- 设置窗口 ----------------
    def open_settings_window(self):
        if not self.settings:
            return
        # 设置窗口只需负责修改 SettingsManager，保存时会自动触发 settings_changed 信号
        # 从而调用上面的 _on_settings_changed 方法
        dlg = self._SettingsDialog(self.settings, parent=self)
        dlg.exec()

    # ---------------- 视觉功能 ----------------
    def _ensure_vision_client(self):
        if self.vision_client or not self.settings:
            return
        
        # 懒加载 QwenVisionClient
        from vision.qwen_vision import QwenVisionClient

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
        max_width = int(pet_geo.width() * 1.8)

        # 读取显示时长
        duration_s = 10
        if self.settings:
            try:
                duration_s = int(self.settings.get("behavior", "temp_bubble_duration_s", default=10))
            except Exception:
                pass

        # 尝试复用现有气泡
        bubble = None
        if self.current_temp_bubble and self.current_temp_bubble.isVisible():
            try:
                self.current_temp_bubble.update_content(text, max_width)
                self.current_temp_bubble.set_lifetime(duration_s)
                bubble = self.current_temp_bubble
            except RuntimeError:
                self.current_temp_bubble = None
        
        if not bubble:
            # 如果旧气泡存在但不可用/不可见，先清理
            if self.current_temp_bubble:
                try:
                    self.current_temp_bubble.close()
                    self.current_temp_bubble.deleteLater()
                except Exception:
                    pass
                self.current_temp_bubble = None

            # 创建新气泡
            bubble = TempBubble(text, max_width, parent=self)
            self.current_temp_bubble = bubble
            # 当气泡销毁时清理引用
            bubble.destroyed.connect(lambda: setattr(self, "current_temp_bubble", None) if self.current_temp_bubble == bubble else None)
            bubble.set_lifetime(duration_s)

        bubble.adjustSize()
        # 气泡位置：桌宠头顶居中
        x = pet_geo.center().x() - bubble.width() // 2
        y = pet_geo.top() - bubble.height() - 10
        bubble.popup(x, y)