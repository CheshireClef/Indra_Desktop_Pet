# src/main.py
import sys
import os
from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
from gui.pet_window import PetWindow
from gui.tray import AppTray
from settings_manager import SettingsManager
from utils import resource_path, ResourceManager

def main():
    app = QApplication(sys.argv)

    # 显示启动画面
    # 使用 ResourceManager 加载资源
    splash_pix = ResourceManager.get_instance().get_image("assets/images/pet.png")
    if not splash_pix.isNull():
        # 稍微放大一点启动图，或者保持原样
        splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        splash.show()
        app.processEvents()  # 确保启动画面渲染
    else:
        splash = None

    # 优化点：复用resource_path，统一路径逻辑（功能和原来完全一致）
    settings_path = resource_path("config/settings.json")
    sm = SettingsManager(settings_path)

    pet = PetWindow(settings_manager=sm)
    pet.show()

    # 关闭启动画面
    if splash:
        splash.finish(pet)

    menu = AppTray.create_main_menu(app, pet)
    pet.set_context_menu(menu)
    # 传递相对路径给 AppTray，由内部 ResourceManager 处理
    tray_icon_path = "assets/images/icon.ico"
    tray = AppTray(app, pet_window=pet, icon_path=tray_icon_path, menu=menu)
    sys.exit(app.exec())
if __name__ == "__main__":
    main()
