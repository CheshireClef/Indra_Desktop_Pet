# src/main.py
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from gui.pet_window import PetWindow
from gui.tray import AppTray
from settings_manager import SettingsManager
from utils import resource_path

def main():
    app = QApplication(sys.argv)

    # 优化点：复用resource_path，统一路径逻辑（功能和原来完全一致）
    settings_path = resource_path("config/settings.json")
    sm = SettingsManager(settings_path)

    pet = PetWindow(settings_manager=sm)
    pet.show()

    menu = AppTray.create_main_menu(app, pet)
    pet.set_context_menu(menu)
    tray_icon_path = resource_path("assets/images/icon.ico")
    tray = AppTray(app, pet_window=pet, icon_path=tray_icon_path, menu=menu)
    sys.exit(app.exec())
if __name__ == "__main__":
    main()
