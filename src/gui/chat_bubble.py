from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QLineEdit, QLabel
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QPropertyAnimation, QEvent, QRect
)
from PySide6.QtGui import QGuiApplication, QPixmap
from utils import resource_path
import os

class ChatBubble(QWidget):
    """
    桌宠对话气泡窗口
    优化点：
    1. append_pet() 时若窗口隐藏，自动浮现
    2. 自动隐藏 + 淡出（失焦）
    3. 显示时自动修正位置，保证不超出屏幕
    """
    send_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # ===== 窗口属性 =====
        self.setWindowTitle("和因陀罗的聊天")
        self.setWindowFlags(
            Qt.Tool |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self.resize(340, 240)

        # ===== UI =====
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setStyleSheet(
            "background: rgba(30,30,30,200);"
            "color: white;"
            "border-radius: 8px;"
            "font-size: 13px;"
        )

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("想和桌宠因陀罗说些什么？")
        self.input_edit.setStyleSheet(
            "background: rgba(255,255,255,230);"
            "border-radius: 6px;"
            "padding: 6px;"
            "color: #000000;"
            "font-size: 13px;"
        )

        layout.addWidget(self.chat_view)
        layout.addWidget(self.input_edit)

        self.input_edit.returnPressed.connect(self._on_enter)

        # ===== 自动隐藏逻辑 =====
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._start_fade_out)

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(300)
        self._fade_anim.finished.connect(self._on_fade_finished)

    def append_pet_silent(self, text: str):
        """
        只写入聊天记录，不触发窗口显示
        """
        was_visible = self.isVisible()

        self.chat_view.append(f"<b>因陀罗：</b>{text}<br>")

        # 如果原本是隐藏的，立刻藏回去
        if not was_visible:
            self.hide()
            
    # ---------- 对话 ----------
    def _on_enter(self):
        text = self.input_edit.text().strip()
        if not text:
            return

        self.input_edit.clear()
        self.append_user(text)
        self.send_message.emit(text)

    def append_user(self, text: str):
        self._ensure_visible()
        self.chat_view.append(f"<b>你：</b>{text}<br>")

    def append_pet(self, text: str):
        # ⭐ 关键优化：桌宠说话时自动浮现
        self._ensure_visible()
        self.chat_view.append(f"<b>因陀罗：</b>{text}<br>")

    # ---------- 可见性与位置 ----------
    def _ensure_visible(self):
        """
        确保窗口显示，并修正到屏幕内
        """
        if not self.isVisible():
            self.show()

        self.raise_()
        self.activateWindow()
        self.setWindowOpacity(1.0)
        self._hide_timer.stop()
        self._fade_anim.stop()

        self._clamp_to_screen()

    def _clamp_to_screen(self):
        """
        防止窗口跑出屏幕
        """
        geo: QRect = self.frameGeometry()
        screen = QGuiApplication.screenAt(geo.center())
        if not screen:
            screen = QGuiApplication.primaryScreen()

        avail = screen.availableGeometry()

        x = geo.x()
        y = geo.y()

        if geo.right() > avail.right():
            x = avail.right() - geo.width() - 10
        if geo.left() < avail.left():
            x = avail.left() + 10
        if geo.bottom() > avail.bottom():
            y = avail.bottom() - geo.height() - 10
        if geo.top() < avail.top():
            y = avail.top() + 10

        self.move(x, y)

    # ---------- 窗口事件 ----------
    def event(self, event):
        if event.type() == QEvent.WindowActivate:
            self._hide_timer.stop()
            self._fade_anim.stop()
            self.setWindowOpacity(1.0)

        elif event.type() == QEvent.WindowDeactivate:
            # 失焦后延迟隐藏
            self._hide_timer.start(2500)

        return super().event(event)

    def showEvent(self, event):
        self._hide_timer.stop()
        self._fade_anim.stop()
        self.setWindowOpacity(1.0)
        super().showEvent(event)
        self.input_edit.setFocus()

        # 显示时也修正一次位置
        self._clamp_to_screen()

    def closeEvent(self, event):
        # 右上角 ❌：只隐藏，不销毁
        event.ignore()
        self.hide()

    # ---------- 动画 ----------
    def _start_fade_out(self):
        self._fade_anim.stop()
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()

    def _on_fade_finished(self):
        if self.windowOpacity() <= 0.05:
            self.hide()
            self.setWindowOpacity(1.0)


class TempBubble(QWidget):
    BUBBLE_PADDING = 25  # 文本与气泡边界的留白(可自由修改)
    GOLDEN_RATIO = 0.618  # 黄金比例
    """优化后的临时聊天气泡（修复重绘/内存泄漏）"""
    def __init__(self, text: str, max_width: int, parent=None):
        super().__init__(parent)

        # 优化窗口标志(跨平台兼容)
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

        # 加载背景图片
        self.bg_image_path = resource_path("assets/images/ui/temp_bubble.png")
        
        # 检查背景图片是否存在并加载
        self.bg_pixmap = None
        if os.path.exists(self.bg_image_path):
            self.bg_pixmap = QPixmap(self.bg_image_path)
            if self.bg_pixmap.isNull():
                print(f"[TempBubble] 背景图片加载失败：{self.bg_image_path}")
                self.bg_pixmap = None
            else:
                print(f"[TempBubble] 背景图片加载成功：{self.bg_image_path}")
        else:
            print(f"[TempBubble] 背景图片不存在：{self.bg_image_path}")

        # 背景层（如果有背景图片）
        if self.bg_pixmap:
            self.bg_label = QLabel(self)
            self.bg_label.setScaledContents(True)
            # 不使用布局，直接用绝对定位
        
        # 文本层（使用绝对定位，不添加到布局）
        self.text_label = QLabel(text, self)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        # 根据是否有背景图片设置不同样式
        if self.bg_pixmap:
            # 有背景图：文本层透明，只显示文字
            self.text_label.setStyleSheet(f"""
                background: transparent;
                color: white;
                padding: {self.BUBBLE_PADDING}px;
            """)
        else:
            # 无背景图：纯色背景
            self.text_label.setStyleSheet(f"""
                background: rgba(40, 40, 40, 210);
                color: white;
                padding: {self.BUBBLE_PADDING}px;
                border-radius: 8px;
            """)
        
        # 计算并应用黄金比例尺寸
        self._calculate_golden_size(text, max_width)

        # 淡出动画(优化销毁逻辑)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(400)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self._on_fade_finished)

        self._life_timer = QTimer(self)
        self._life_timer.setSingleShot(True)
        self._life_timer.timeout.connect(self._fade_anim.start)

    def _calculate_golden_size(self, text: str, max_width: int):
        """
        计算符合黄金比例的气泡尺寸（终极修复版）
        核心改进：
        1. 使用实际 QLabel 测量真实渲染尺寸（而非 QFontMetrics 理论值）
        2. CSS padding 已包含在测量中，确保文本完整显示
        3. 主动搜索最接近黄金比例的宽度
        """
        # 创建临时测量标签（应用相同样式）
        temp_label = QLabel(text)
        temp_label.setWordWrap(True)
        temp_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        # 应用相同的样式
        if self.bg_pixmap:
            temp_label.setStyleSheet(f"""
                background: transparent;
                color: white;
                padding: {self.BUBBLE_PADDING}px;
            """)
        else:
            temp_label.setStyleSheet(f"""
                background: rgba(40, 40, 40, 210);
                color: white;
                padding: {self.BUBBLE_PADDING}px;
                border-radius: 8px;
            """)
        
        # 定义搜索范围（注意：这里是包含 padding 的总宽度）
        min_bubble_width = 150
        max_bubble_width = max_width
        
        # 存储最优方案
        best_width = max_bubble_width
        best_height = 0
        best_ratio_diff = float('inf')
        
        # 阶段1：粗搜索（步长 25px）
        step = 25
        for test_width in range(min_bubble_width, max_bubble_width + 1, step):
            # 设置测试宽度并让 QLabel 自适应高度
            temp_label.setFixedWidth(test_width)
            temp_label.adjustSize()
            
            # 获取实际渲染后的高度（包含 padding）
            test_height = temp_label.height()
            
            # 计算当前高宽比
            current_ratio = test_height / test_width if test_width > 0 else 0
            ratio_diff = abs(current_ratio - self.GOLDEN_RATIO)
            
            # 记录最接近黄金比例的配置
            if ratio_diff < best_ratio_diff:
                best_ratio_diff = ratio_diff
                best_width = test_width
                best_height = test_height
        
        # 阶段2：精细搜索（在最优宽度附近 ±50px，步长 5px）
        fine_search_start = max(min_bubble_width, best_width - 50)
        fine_search_end = min(max_bubble_width, best_width + 50)
        
        for test_width in range(fine_search_start, fine_search_end + 1, 5):
            temp_label.setFixedWidth(test_width)
            temp_label.adjustSize()
            test_height = temp_label.height()
            
            current_ratio = test_height / test_width if test_width > 0 else 0
            ratio_diff = abs(current_ratio - self.GOLDEN_RATIO)
            
            if ratio_diff < best_ratio_diff:
                best_ratio_diff = ratio_diff
                best_width = test_width
                best_height = test_height
        
        # 最终验证：使用最优宽度再次测量，确保准确
        temp_label.setFixedWidth(best_width)
        temp_label.adjustSize()
        final_width = best_width
        final_height = temp_label.height()
        
        # 安全边界检查
        final_width = max(150, min(final_width, max_width))
        final_height = max(50, final_height)
        
        # 设置整体窗口尺寸
        self.setFixedSize(final_width, final_height)
        
        # 如果有背景图片，缩放并应用到背景层（绝对定位）
        if self.bg_pixmap:
            scaled_bg = self.bg_pixmap.scaled(
                final_width, final_height,
                Qt.IgnoreAspectRatio,  # 拉伸填充
                Qt.SmoothTransformation
            )
            self.bg_label.setPixmap(scaled_bg)
            # 背景层完全覆盖整个窗口
            self.bg_label.setGeometry(0, 0, final_width, final_height)
            # 确保背景在底层
            self.bg_label.lower()
        
        # 文本层也使用绝对定位，完全覆盖整个窗口
        self.text_label.setGeometry(0, 0, final_width, final_height)
        
        # 如果有背景，确保文本层在上方
        if self.bg_pixmap:
            self.text_label.raise_()
        
        # 清理临时对象
        temp_label.deleteLater()

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
