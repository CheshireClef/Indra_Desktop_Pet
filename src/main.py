# src/main.py
"""
主程序入口文件
负责初始化 QApplication，加载启动画面，配置全局设置，并启动主窗口 (PetWindow) 和系统托盘 (AppTray)。
"""
import sys
import time

from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtCore import Qt

from gui.pet_window import PetWindow
from gui.tray import AppTray
from settings_manager import SettingsManager
from utils import resource_path, ResourceManager


def _splash_message(splash: QSplashScreen | None, app: QApplication, text: str) -> None:
    if not splash:
        return
    splash.showMessage(
        text,
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        Qt.GlobalColor.white,
    )
    app.processEvents()


def main():
    t0 = time.perf_counter()
    app = QApplication(sys.argv)

    splash_pix = ResourceManager.get_instance().get_image("assets/images/pet.png")
    if not splash_pix.isNull():
        splash = QSplashScreen(splash_pix, Qt.WindowType.WindowStaysOnTopHint)
        splash.show()
        app.processEvents()
    else:
        splash = None

    _splash_message(splash, app, "正在加载配置…")
    t_cfg = time.perf_counter()
    settings_path = resource_path("config/settings.json")
    sm = SettingsManager(settings_path)
    print(f"[Startup] 配置加载 {time.perf_counter() - t_cfg:.2f}s")

    _splash_message(splash, app, "正在初始化桌宠…")
    t_pet = time.perf_counter()
    pet = PetWindow(settings_manager=sm, splash=splash)
    print(f"[Startup] 桌宠窗口 {time.perf_counter() - t_pet:.2f}s")

    _splash_message(splash, app, "正在加载系统托盘…")
    menu = AppTray.create_main_menu(app, pet)
    pet.set_context_menu(menu)
    tray_icon_path = "assets/images/icon.ico"
    tray = AppTray(app, pet_window=pet, icon_path=tray_icon_path, menu=menu)

    print(f"[Startup] 启动完成，总耗时 {time.perf_counter() - t0:.2f}s")
    sys.exit(app.exec())
if __name__ == "__main__":
    main()
