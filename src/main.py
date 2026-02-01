# src/main.py
"""
主程序入口文件
负责初始化 QApplication，加载启动画面，配置全局设置，并启动主窗口 (PetWindow) 和系统托盘 (AppTray)。
"""
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
    # 初始化 Qt 应用程序对象，它是所有 GUI 程序的控制中心
    app = QApplication(sys.argv)

    # 显示启动画面
    # 使用 ResourceManager 加载资源
    splash_pix = ResourceManager.get_instance().get_image("assets/images/pet.png")
    if not splash_pix.isNull():
        # 稍微放大一点启动图，或者保持原样
        # WindowStaysOnTopHint 确保启动画面始终在最上层
        splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        splash.show()
        app.processEvents()  # 确保启动画面渲染，避免白屏
    else:
        splash = None

    # 优化点：复用resource_path，统一路径逻辑（功能和原来完全一致）
    # 配置文件路径：在开发环境和打包环境中都能正确定位
    settings_path = resource_path("config/settings.json")
    sm = SettingsManager(settings_path)

    # 初始化主窗口（桌宠）
    pet = PetWindow(settings_manager=sm)
    pet.show()

    # 关闭启动画面
    # 当主窗口初始化完成并显示后，关闭启动画面
    if splash:
        splash.finish(pet)

    # 创建并设置系统托盘菜单
    menu = AppTray.create_main_menu(app, pet)
    pet.set_context_menu(menu)
    # 传递相对路径给 AppTray，由内部 ResourceManager 处理
    tray_icon_path = "assets/images/icon.ico"
    # 初始化系统托盘图标
    tray = AppTray(app, pet_window=pet, icon_path=tray_icon_path, menu=menu)
    
    # 进入应用程序的主事件循环
    sys.exit(app.exec())
if __name__ == "__main__":
    main()
