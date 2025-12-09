# src/gui/tray.py (替换用)
import os
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction

class AppTray:
    """
    系统托盘管理类。
    - 使用 AppTray.create_main_menu(app, pet_window) 创建一份统一的 QMenu。
    - 传入 menu 给 PetWindow（立绘右键）和 AppTray（托盘右键）以实现同步菜单。
    """

    def __init__(self, app, pet_window, icon_path: str = None, menu: QMenu | None = None):
        self.app = app
        self.window = pet_window

        # icon
        if icon_path and os.path.exists(icon_path):
            icon = QIcon(icon_path)
        else:
            icon = app.style().standardIcon(getattr(app.style(), 'SP_ComputerIcon'))

        self.tray = QSystemTrayIcon(icon, app)

        # 使用外部传入的 menu 或者自行创建（建议统一创建一次并传入）
        if menu is None:
            self.menu = self.create_main_menu(app, pet_window)
        else:
            self.menu = menu

        # 将创建好的 menu 绑定到托盘
        self.tray.setContextMenu(self.menu)

        # tray activated handler (double click toggles visibility)
        self.tray.activated.connect(self._on_activated)

        self.tray.show()

    @staticmethod
    def create_main_menu(app, pet_window):
        """
        创建并返回主右键菜单（QMenu）。
        - 所有 QAction 都以 menu 作为 parent，且把引用保存到 menu._actions_refs 中，
          防止被 Python 垃圾回收导致菜单项消失的问题。
        - 在这里统一添加/移除菜单项，PetWindow 和 AppTray 共享同一份 menu。
        """
        menu = QMenu()

        # 用于防止 QAction 被回收：把所有 action 保存在 menu 的私有列表中
        menu._actions_refs = []

        # ---- 显示桌宠 ----
        show_action = QAction("显示桌宠", menu)
        def on_show():
            try:
                pet_window.show_window()
            except Exception:
                pass
        show_action.triggered.connect(on_show)
        menu.addAction(show_action)
        menu._actions_refs.append(show_action)

        # ---- 隐藏桌宠 ----
        hide_action = QAction("隐藏桌宠", menu)
        def on_hide():
            try:
                pet_window.hide_window()
            except Exception:
                pass
        hide_action.triggered.connect(on_hide)
        menu.addAction(hide_action)
        menu._actions_refs.append(hide_action)

        menu.addSeparator()

        # ---- 示例: 屏幕监视 开/关（占位） ----
        screen_watch_action = QAction("屏幕监视：关闭", menu)
        def toggle_screen_watch():
            # 示例：如果 pet_window 有 screen_watcher 并支持 toggle()
            try:
                if hasattr(pet_window, "screen_watcher") and getattr(pet_window, "screen_watcher") is not None:
                    pet_window.screen_watcher.toggle()
                    enabled = bool(getattr(pet_window.screen_watcher, "enabled", False))
                    screen_watch_action.setText("屏幕监视：开启" if enabled else "屏幕监视：关闭")
            except Exception:
                # 出错时忽略（占位）
                pass
        screen_watch_action.triggered.connect(toggle_screen_watch)
        menu.addAction(screen_watch_action)
        menu._actions_refs.append(screen_watch_action)

        menu.addSeparator()

        # ---- 可扩展项：打开设置 界面（示例） ----
        settings_action = QAction("设置", menu)
        def open_settings():
            # 期望 pet_window 提供 open_settings_window() 或者你可以在这里打开自定义窗口
            try:
                if hasattr(pet_window, "open_settings_window"):
                    pet_window.open_settings_window()
                else:
                    # 如果没有实现，你可以在此处放置一个占位行为
                    print("[Tray] open_settings requested but PetWindow has no open_settings_window() method.")
            except Exception:
                pass
        settings_action.triggered.connect(open_settings)
        menu.addAction(settings_action)
        menu._actions_refs.append(settings_action)

        # ---- 退出 ----
        menu.addSeparator()
        quit_action = QAction("退出", menu)
        def on_quit():
            try:
                pet_window.close()
            except Exception:
                pass
            app.quit()
        quit_action.triggered.connect(on_quit)
        menu.addAction(quit_action)
        menu._actions_refs.append(quit_action)

        return menu

    # ---------- instance slots ----------
    def _on_activated(self, reason):
        # double click toggles visibility
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.DoubleClick:
            try:
                self.window.toggle_visibility()
            except Exception:
                pass
