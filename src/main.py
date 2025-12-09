# src/main.py
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from gui.pet_window import PetWindow
from gui.tray import AppTray

def resource_path(rel_path: str) -> str:
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base, rel_path)

def main():
    app = QApplication(sys.argv)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

    pet = PetWindow(image_path=resource_path("assets/images/pet.png"))

    # 先让 pet 初始化显示内容（位置、大小）
    pet.show()

    # 统一创建主菜单并传入 pet（这样同一份 menu 同时用于 tray 与 pet）
    menu = AppTray.create_main_menu(app, pet)

    # 把 menu 绑定到 pet（右键会显示）
    pet.set_context_menu(menu)

    # 创建 tray，并把 menu 传入（tray 会使用同一份 menu）
    tray_icon_path = resource_path("assets/images/icon.ico")
    tray = AppTray(app, pet_window=pet, icon_path=tray_icon_path, menu=menu)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
