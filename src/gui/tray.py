"""
系统托盘模块
负责管理任务栏托盘图标 (System Tray Icon) 及其右键菜单。
"""
import os
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
import webbrowser  # 新增：导入浏览器模块
from utils import resource_path, ResourceManager
from PySide6.QtWidgets import QStyle

class AppTray:
    """
    系统托盘管理类
    - create_main_menu 会返回一个 menu
    - menu._actions_refs 用于外部联动更新文本 / 状态
    """
    def __init__(self, app, pet_window, icon_path: str = None, menu: QMenu | None = None):
        self.app = app
        self.window = pet_window

        # 核心修改：使用 ResourceManager 加载图标
        if icon_path:
            icon = ResourceManager.get_instance().get_icon(icon_path)
            # 如果加载失败（返回空图标），使用默认图标
            if icon.isNull():
                icon = app.style().standardIcon(QStyle.SP_DesktopIcon)
        else:
            icon = app.style().standardIcon(QStyle.SP_DesktopIcon)

        self.tray = QSystemTrayIcon(icon, app)

        if menu is None:
            self.menu = self.create_main_menu(app, pet_window)
        else:
            self.menu = menu

        self.tray.setContextMenu(self.menu)
        # 处理托盘图标点击事件 (例如点击恢复窗口)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

        # 绑定配置变更信号，实现菜单文字实时刷新
        from settings_manager import SettingsManager
        self.sm = SettingsManager.get_instance()
        if self.sm:
            self.sm.settings_changed.connect(self._update_menu_status)

    def _update_menu_status(self):
        """配置变更时刷新菜单项文本 (如：屏幕监视、长期记忆的开启/关闭状态)"""
        if not self.menu:
            return
        refs = getattr(self.menu, "_actions_refs", None) or {}
        try:
            if "screen_watch" in refs:
                enabled = self.sm.get("behavior", "screen_watch_enabled", default=False)
                refs["screen_watch"].setText("屏幕监视：开启" if enabled else "屏幕监视：关闭")
            if "long_term_memory" in refs:
                enabled = self.sm.get("behavior", "long_term_memory_enabled", default=False)
                refs["long_term_memory"].setText("长期记忆：开启" if enabled else "长期记忆：关闭")
        except Exception:
            pass

    @staticmethod
    def create_main_menu(app, pet_window):
        """创建右键菜单"""
        menu = QMenu()
        # 用于存储 action 引用，方便后续修改（如更改文本）
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
                
                # 注意：
                # 1. sm.set 会触发 settings_changed 信号
                # 2. AppTray._update_menu_status 会响应信号更新菜单文字
                # 3. PetWindow._on_settings_changed 会响应信号更新功能状态
                # 因此无需手动更新 text 或调用 _apply_screen_watch_settings

            except Exception as e:
                print("[Tray] toggle_screen_watch error:", e)

        screen_watch_action.triggered.connect(toggle_screen_watch)
        menu.addAction(screen_watch_action)
        menu._actions_refs["screen_watch"] = screen_watch_action

        # ---- 长期记忆 开 / 关 ----
        ltm_enabled = False
        try:
            if hasattr(pet_window, "settings") and pet_window.settings:
                ltm_enabled = bool(
                    pet_window.settings.get(
                        "behavior", "long_term_memory_enabled", default=False
                    )
                )
        except Exception:
            ltm_enabled = False
        ltm_text = "长期记忆：开启" if ltm_enabled else "长期记忆：关闭"
        long_term_memory_action = QAction(ltm_text, menu)

        def toggle_long_term_memory():
            try:
                sm = getattr(pet_window, "settings", None)
                if not sm:
                    return
                current = bool(sm.get("behavior", "long_term_memory_enabled", default=False))
                sm.set("behavior", "long_term_memory_enabled", value=not current)
            except Exception as e:
                print("[Tray] toggle_long_term_memory error:", e)

        long_term_memory_action.triggered.connect(toggle_long_term_memory)
        menu.addAction(long_term_memory_action)
        menu._actions_refs["long_term_memory"] = long_term_memory_action

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
                # 核心修改：改用 resource_path 获取用户手册路径
                manual_path = resource_path("用户手册.html")  # 相对根目录的路径
                # 转换为浏览器可识别的file协议路径（兼容Windows/macOS/Linux）
                manual_url = f"file:///{os.path.normpath(manual_path)}"
                # 打开手册
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
