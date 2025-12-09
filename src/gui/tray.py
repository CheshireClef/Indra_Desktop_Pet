# src/gui/tray.py
import os
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction

class AppTray:
    """
    系统托盘管理类（改进版）
    - create_main_menu 会返回一个 menu，其中 menu._actions_refs 是 dict，
      键名便于外部查找并修改对应 QAction（例如更新文本、启用/禁用等）。
    """
    def __init__(self, app, pet_window, icon_path: str = None, menu: QMenu | None = None):
        self.app = app
        self.window = pet_window

        if icon_path and os.path.exists(icon_path):
            icon = QIcon(icon_path)
        else:
            icon = app.style().standardIcon(getattr(app.style(), 'SP_ComputerIcon'))

        self.tray = QSystemTrayIcon(icon, app)

        if menu is None:
            self.menu = self.create_main_menu(app, pet_window)
        else:
            self.menu = menu

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

    @staticmethod
    def create_main_menu(app, pet_window):
        """
        统一创建并返回主菜单（QMenu）。
        菜单项引用保存在 menu._actions_refs 字典中：
          menu._actions_refs['screen_watch'] -> QAction
        """
        menu = QMenu()
        menu._actions_refs = {}

        # ---- 显示桌宠 ----
        show_action = QAction("显示桌宠", menu)
        show_action.triggered.connect(lambda: getattr(pet_window, "show_window", lambda: None)())
        menu.addAction(show_action)
        menu._actions_refs['show'] = show_action

        # ---- 隐藏桌宠 ----
        hide_action = QAction("隐藏桌宠", menu)
        hide_action.triggered.connect(lambda: getattr(pet_window, "hide_window", lambda: None)())
        menu.addAction(hide_action)
        menu._actions_refs['hide'] = hide_action

        menu.addSeparator()

        # ---- 屏幕监视 开/关 ----
        # 初始文本根据 settings（如果存在）来设
        enabled = False
        try:
            if hasattr(pet_window, "settings") and pet_window.settings:
                enabled = bool(pet_window.settings.get("behavior", "screen_watch_enabled", default=False))
        except Exception:
            enabled = False
        sw_text = "屏幕监视：开启" if enabled else "屏幕监视：关闭"
        screen_watch_action = QAction(sw_text, menu)

        def toggle_screen_watch():
            """切换 settings 中的 screen_watch_enabled 并更新菜单文本"""
            try:
                sm = getattr(pet_window, "settings", None)
                if sm:
                    current = bool(sm.get("behavior", "screen_watch_enabled", default=False))
                    new = not current
                    sm.set("behavior", "screen_watch_enabled", value=new)
                    # 更新菜单文本
                    screen_watch_action.setText("屏幕监视：开启" if new else "屏幕监视：关闭")
                    # 如果 pet_window 实现了相应的启停接口，调用它（可选）
                    if hasattr(pet_window, "on_screen_watch_toggled"):
                        try:
                            pet_window.on_screen_watch_toggled(new)
                        except Exception:
                            pass
            except Exception:
                pass

        screen_watch_action.triggered.connect(toggle_screen_watch)
        menu.addAction(screen_watch_action)
        menu._actions_refs['screen_watch'] = screen_watch_action

        menu.addSeparator()

        # ---- 设置 ----
        settings_action = QAction("设置", menu)
        def open_settings():
            try:
                # 打开设置对话框（PetWindow.open_settings_window 会在保存后更新菜单）
                if hasattr(pet_window, "open_settings_window"):
                    pet_window.open_settings_window()
            except Exception:
                pass
        settings_action.triggered.connect(open_settings)
        menu.addAction(settings_action)
        menu._actions_refs['settings'] = settings_action

        menu.addSeparator()

        # ---- 退出 ----
        quit_action = QAction("退出", menu)
        def on_quit():
            try:
                if hasattr(pet_window, "close"):
                    pet_window.close()
            except Exception:
                pass
            app.quit()
        quit_action.triggered.connect(on_quit)
        menu.addAction(quit_action)
        menu._actions_refs['quit'] = quit_action

        return menu

    def _on_activated(self, reason):
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.DoubleClick:
            try:
                self.window.toggle_visibility()
            except Exception:
                pass
