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
from workers.chat_worker import ChatWorker


class PetWindow(QWidget):
    """
    桌宠主窗口类
    继承自 QWidget，设置为无边框、透明背景、置顶显示。
    """
    # 窗口可见性切换信号
    toggled_visibility = Signal(bool)

    def __init__(
        self,
        settings_manager=None,
        icon_path: str = None,
        image_path: str = "",
        splash=None,
    ):
        super().__init__(None, Qt.Window)

        self._splash = splash

        # 延迟导入避免循环依赖（ChatManager 会拉取 llama_index/torch，勿在 __init__ 导入）
        from .animation import AnimationDriver
        from .chat_bubble import ChatBubble
        from .settings_dialog import SettingsDialog

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
        self._chat_worker = None

        # 保存类引用
        self._AnimationDriver = AnimationDriver
        self._ChatBubble = ChatBubble
        self._SettingsDialog = SettingsDialog

        # 初始化流程
        self._setup_window()
        # 新增：初始化表情Label
        self._setup_emoji_label()
        self._setup_animation()
        self._load_image(reset_pos=True)
        # 首帧与缩放就绪后再显示桌宠、关闭 splash（信号须在连接后手动触发）
        if self.animation.get_idle_first_frame():
            self._on_idle_frames_loaded()

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
        """动画首帧就绪后显示桌宠并关闭启动画面。"""
        self.show()
        self.raise_()
        self.update()
        if self._splash is not None:
            self._splash.finish(self)
            self._splash = None

    # ---------------- 聊天功能 ----------------
    def _setup_chat(self):
        from llm.chat_manager import ChatManager

        persona_path = resource_path("src/llm/persona.txt")
        self.chat_manager = ChatManager(self.settings, persona_path)
        
        if hasattr(self.chat_manager, 'knowledge_base'):
            self.chat_manager.knowledge_base.indices_loaded.connect(self._on_indices_loaded)
            self.chat_manager.knowledge_base.model_loaded_to_cpu.connect(self._on_model_loaded_to_cpu)
            self.chat_manager.knowledge_base.load_failed.connect(self._on_load_failed)
            try:
                self.chat_manager.knowledge_base.rebuild_started.connect(self._on_rebuild_started)
            except Exception:
                pass
            
            # 启动加载（确保信号连接后再启动，避免竞态条件）
            self.chat_manager.knowledge_base.start_loading()

        # 初始化聊天气泡，传入字体大小
        font_size = 13
        if self.settings:
            font_size = self.settings.get("pet", "font_size", default=13)
        self.chat_bubble = self._ChatBubble(font_size=font_size)
        self.chat_bubble.send_message.connect(self._on_user_message)

    def _on_model_loaded_to_cpu(self):
        """模型加载到CPU后的回调"""
        print("[PetWindow] 收到模型加载完成信号")
        self._show_temp_bubble(
            "剧情库加载中，请稍候…加载完成前不会检索剧情库，可正常聊天"
        )

    def _on_indices_loaded(self):
        """知识库索引加载完成后的回调"""
        print("[PetWindow] 收到索引加载完成信号")
        self._show_temp_bubble("数据库加载完成")

    def _on_rebuild_started(self, name: str):
        print(f"[PetWindow] 检测到{name}索引开始重建")
        self._show_temp_bubble("检测到知识库数据更新，正在重建索引，这可能需要一段时间")

    def _on_load_failed(self, msg: str):
        """知识库加载失败的回调"""
        print(f"[PetWindow] 收到加载失败信号：{msg}")
        self._show_temp_bubble(f"数据库加载失败：{msg}")

    def _on_user_message(self, text: str):
        """用户消息已在 ChatBubble 内即时显示；LLM 请求放后台线程。"""
        if self._chat_worker and self._chat_worker.isRunning():
            return
        if not hasattr(self, "chat_manager") or not self.chat_manager:
            self._show_temp_bubble("聊天功能尚未就绪，请稍候")
            return

        self.chat_bubble.set_waiting(True)
        self._chat_worker = ChatWorker(self.chat_manager, text)
        self._chat_worker.success.connect(self._on_chat_worker_success)
        self._chat_worker.failed.connect(self._on_chat_worker_failed)
        self._chat_worker.finished.connect(self._on_chat_worker_finished)
        self._chat_worker.start()

    def _on_chat_worker_success(self, reply: str, emotion_tag: str, reasoning):
        self.chat_bubble.append_pet(reply, reasoning=reasoning)
        self._show_emotion_emoji(emotion_tag)

    def _on_chat_worker_failed(self, error_message: str):
        self._show_temp_bubble(error_message)

    def _on_chat_worker_finished(self):
        self.chat_bubble.set_waiting(False)
        self._chat_worker = None

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
        
        # 1.1 刷新字体大小
        if hasattr(self, 'chat_bubble') and self.chat_bubble:
            try:
                font_size = int(self.settings.get("pet", "font_size", default=13))
                self.chat_bubble.set_font_size(font_size)
            except Exception:
                pass

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
        
        # 4. 视觉/模型配置热更新：清空懒加载客户端，下次观察时按新配置重建
        self.vision_client = None
        try:
            from llm.model_service import ModelService
            ModelService.reset_cache()
        except Exception:
            pass

        self.update()

    # ---------------- 设置窗口 ----------------
    def open_settings_window(self):
        if not self.settings:
            return
        try:
            ltm = None
            if getattr(self, "chat_manager", None):
                ltm = self.chat_manager.get_long_term_memory()
            # 勿以 PetWindow 为父窗口：其含 WindowDoesNotAcceptFocus，打包后模态设置框可能无法显示
            dlg = self._SettingsDialog(
                self.settings,
                parent=None,
                long_term_memory=ltm,
            )
            dlg.setWindowFlags(
                Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint
            )
            dlg.exec()
        except Exception as e:
            print(f"[PetWindow] 打开设置失败: {e}")
            import traceback
            traceback.print_exc()
            self._show_temp_bubble(f"打开设置失败：{e}")

    # ---------------- 视觉功能 ----------------
    def _ensure_vision_client(self):
        if self.vision_client or not self.settings:
            return

        from llm.model_service import ModelService
        from llm.providers.registry import requires_api_key

        binding = self.settings.get_vision_binding()
        vendor = binding.get("vendor", "custom_openai")
        api_key = binding.get("api_key") or ""
        if requires_api_key(vendor) and not api_key:
            print("[Vision] API 密钥为空，视觉功能禁用")
            return
        ms = ModelService.get_instance(self.settings)
        client = ms.get_vision_client()
        if not client:
            print("[Vision] 视觉客户端初始化失败，请检查识图模型配置")
            return
        # 兼容 ScreenObserveWorker：保留 describe_image 接口
        self.vision_client = client

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
        # 错误信息标红（含 LLM 空回复、通用错误前缀）
        if text.startswith(("屏幕观察出错：", "定时屏幕观察出错：", "屏幕观察功能未启用：", "LLM 返回了空回复", "错误：")):
            text = f"<font color='#ff4444'>{text}</font>"

        pet_geo = self.geometry()
        max_width = int(pet_geo.width() * 1.8)

        # 读取配置
        duration_s = 10
        font_size = 13
        if self.settings:
            try:
                duration_s = int(self.settings.get("behavior", "temp_bubble_duration_s", default=10))
                font_size = int(self.settings.get("pet", "font_size", default=13))
            except Exception:
                pass

        # 尝试复用现有气泡
        bubble = None
        if self.current_temp_bubble and self.current_temp_bubble.isVisible():
            try:
                self.current_temp_bubble.set_font_size(font_size)
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
            bubble = TempBubble(text, max_width, parent=self, font_size=font_size)
            self.current_temp_bubble = bubble
            # 当气泡销毁时清理引用
            bubble.destroyed.connect(lambda: setattr(self, "current_temp_bubble", None) if self.current_temp_bubble == bubble else None)
            bubble.set_lifetime(duration_s)

        bubble.adjustSize()
        # 气泡位置：桌宠头顶居中
        x = pet_geo.center().x() - bubble.width() // 2
        y = pet_geo.top() - bubble.height() - 10
        bubble.popup(x, y)
