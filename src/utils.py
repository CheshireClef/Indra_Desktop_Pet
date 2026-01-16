# src/utils.py
import os
import sys

def resource_path(rel_path: str) -> str:
    """
    统一资源路径处理：
    - 开发环境：以工程根目录为基准
    - PyInstaller：以 _internal (sys._MEIPASS) 为基准
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    return os.path.join(base, rel_path)
