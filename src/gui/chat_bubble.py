from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QLineEdit
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QPropertyAnimation, QEvent
)


class ChatBubble(QWidget):
    """
    桌宠对话气泡窗口
    - 窗口失活（切换到其他程序）后延迟淡出并隐藏
    - 再次打开聊天记录保留
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
        )

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("想和桌宠因陀罗说些什么？")
        self.input_edit.setStyleSheet(
            "background: rgba(255,255,255,230);"
            "border-radius: 6px;"
            "padding: 6px;"
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

    # ---------- 对话 ----------
    def _on_enter(self):
        text = self.input_edit.text().strip()
        if not text:
            return

        self.input_edit.clear()
        self.append_user(text)
        self.send_message.emit(text)

    def append_user(self, text: str):
        self.chat_view.append(f"<b>你：</b>{text}")

    def append_pet(self, text: str):
        self.chat_view.append(f"<b>因陀罗：</b>{text}")

    # ---------- 窗口事件（关键修复点） ----------
    def event(self, event):
        if event.type() == QEvent.WindowActivate:
            # 用户切回来了
            self._hide_timer.stop()
            self._fade_anim.stop()
            self.setWindowOpacity(1.0)

        elif event.type() == QEvent.WindowDeactivate:
            # 用户切走了（切应用 / 点别处）
            self._hide_timer.start(2500)

        return super().event(event)

    def showEvent(self, event):
        self._hide_timer.stop()
        self._fade_anim.stop()
        self.setWindowOpacity(1.0)
        super().showEvent(event)
        self.input_edit.setFocus()

    def closeEvent(self, event):
        # 点右上角 ❌ 时不销毁，只隐藏
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
