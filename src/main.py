# src/main.py
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from gui.pet_window import PetWindow
from gui.tray import AppTray
from settings_manager import SettingsManager

def resource_path(rel_path: str) -> str:
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base, rel_path)

def main():
    app = QApplication(sys.argv)

    # settings
    settings_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "settings.json"))
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
