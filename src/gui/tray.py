import os
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
import webbrowser  # 新增：导入浏览器模块

class AppTray:
    """
    系统托盘管理类
    - create_main_menu 会返回一个 menu
    - menu._actions_refs 用于外部联动更新文本 / 状态
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
        menu = QMenu()
        menu._actions_refs = {}

        # ---- 显示桌宠 ----
        show_action = QAction("显示桌宠", menu)
        show_action.triggered.connect(
            lambda: getattr(pet_window, "show_window", lambda: None)()
        )
        menu.addAction(show_action)
        menu._actions_refs["show"] = show_action

        # ---- 隐藏桌宠 ----
        hide_action = QAction("隐藏桌宠", menu)
        hide_action.triggered.connect(
            lambda: getattr(pet_window, "hide_window", lambda: None)()
        )
        menu.addAction(hide_action)
        menu._actions_refs["hide"] = hide_action

        menu.addSeparator()

        # ---- ⭐ 手动：观察屏幕（Step 1） ----
        observe_action = QAction("观察屏幕", menu)

        def observe_once():
            try:
                if hasattr(pet_window, "observe_screen_and_comment"):
                    pet_window.observe_screen_and_comment()
            except Exception as e:
                print("[Tray] observe_once error:", e)


        observe_action.triggered.connect(observe_once)
        menu.addAction(observe_action)
        menu._actions_refs["observe_screen"] = observe_action

        menu.addSeparator()

        # ---- 屏幕监视 开 / 关（自动） ----
        enabled = False
        try:
            if hasattr(pet_window, "settings") and pet_window.settings:
                enabled = bool(
                    pet_window.settings.get(
                        "behavior", "screen_watch_enabled", default=False
                    )
                )
        except Exception:
            enabled = False

        sw_text = "屏幕监视：开启" if enabled else "屏幕监视：关闭"
        screen_watch_action = QAction(sw_text, menu)

        def toggle_screen_watch():
            try:
                sm = getattr(pet_window, "settings", None)
                if not sm:
                    return

                current = bool(
                    sm.get("behavior", "screen_watch_enabled", default=False)
                )
                new = not current
                sm.set("behavior", "screen_watch_enabled", value=new)

                screen_watch_action.setText(
                    "屏幕监视：开启" if new else "屏幕监视：关闭"
                )

                # 核心修复：调用PetWindow的方法使配置实时生效
                # 替代原来不存在的 on_screen_watch_toggled 方法
                if hasattr(pet_window, "_apply_screen_watch_settings"):
                    pet_window._apply_screen_watch_settings()

            except Exception as e:
                print("[Tray] toggle_screen_watch error:", e)

        screen_watch_action.triggered.connect(toggle_screen_watch)
        menu.addAction(screen_watch_action)
        menu._actions_refs["screen_watch"] = screen_watch_action

        menu.addSeparator()

        # ---- 设置 ----
        settings_action = QAction("设置", menu)
        settings_action.triggered.connect(
            lambda: getattr(pet_window, "open_settings_window", lambda: None)()
        )
        menu.addAction(settings_action)
        menu._actions_refs["settings"] = settings_action

        menu.addSeparator()

         # ========== 新增：打开使用说明 ==========
        menu.addSeparator()
        manual_action = QAction("打开使用说明", menu)

        def open_user_manual():
            try:
                # 1. 获取当前tray.py的绝对路径（src/gui/tray.py）
                current_file = os.path.abspath(__file__)
                # 2. 向上回溯3级目录：src/gui/tray.py → src/gui → src → 根目录
                root_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
                # 3. 拼接根目录下的「用户手册.html」路径
                manual_path = os.path.join(root_dir, "用户手册.html")
                # 4. 转换为浏览器可识别的file协议路径（兼容Windows/macOS/Linux）
                manual_url = f"file:///{os.path.normpath(manual_path)}"
                # 5. 打开手册
                webbrowser.open(manual_url)
            except Exception as e:
                print("[Tray] open_user_manual error:", e)

        manual_action.triggered.connect(open_user_manual)
        menu.addAction(manual_action)
        menu._actions_refs["user_manual"] = manual_action
        # ========== 新增结束 ==========
        menu.addSeparator()
        # ---- 退出 ----
        quit_action = QAction("退出", menu)

        def on_quit():
            try:
                if hasattr(pet_window, "close"):
                    pet_window.close()
            finally:
                app.quit()

        quit_action.triggered.connect(on_quit)
        menu.addAction(quit_action)
        menu._actions_refs["quit"] = quit_action

        return menu

    def _on_activated(self, reason):
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.DoubleClick:
            try:
                self.window.toggle_visibility()
            except Exception:
                pass
