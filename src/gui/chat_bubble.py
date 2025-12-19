from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QLineEdit
)
from PySide6.QtCore import Qt, Signal


class ChatBubble(QWidget):
    """
    桌宠对话气泡窗口
    """
    send_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # 无边框、置顶、小窗口
        self.setWindowFlags(
            Qt.Tool
            | Qt.WindowStaysOnTopHint
        )

        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.resize(320, 220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 显示对话内容（只读）
        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setStyleSheet(
            "background: rgba(30,30,30,180); color: white; border-radius: 8px;"
        )

        # 输入框
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("想和桌宠因陀罗说些什么？")
        self.input_edit.setStyleSheet(
            "background: rgba(255,255,255,220); border-radius: 6px; padding: 6px;"
        )

        layout.addWidget(self.chat_view)
        layout.addWidget(self.input_edit)

        # 绑定回车发送
        self.input_edit.returnPressed.connect(self._on_enter)

    def _on_enter(self):
        text = self.input_edit.text().strip()
        if not text:
            return

        self.input_edit.clear()
        self.append_user(text)
        self.send_message.emit(text)

    # ---------- 公共接口 ----------
    def append_user(self, text: str):
        self.chat_view.append(f"<b>你：</b>{text}")

    def append_pet(self, text: str):
        self.chat_view.append(f"<b>因陀罗：</b>{text}")
