# src/utils.py
"""
工具函数和通用类模块
包含资源路径处理 (兼容开发环境和 PyInstaller 打包环境) 以及资源管理器单例 (ResourceManager)。
"""
import os
import sys
from PySide6.QtGui import QPixmap, QIcon

def resource_path(rel_path: str) -> str:
    """
    统一资源路径处理：
    - 开发环境：以工程根目录为基准
    - PyInstaller：以 _internal (sys._MEIPASS) 为基准
    """
    # sys.frozen 是 PyInstaller 打包后的标志
    # sys._MEIPASS 是打包后的临时解压目录
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        # 开发环境下，定位到当前文件 (src/utils.py) 的上一级目录 (即项目根目录)
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    return os.path.join(base, rel_path)

class ResourceManager:
    """
    资源管理器单例
    负责统一加载图片、图标等资源，并提供简单的缓存机制，避免重复 IO 操作。
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        """获取单例实例，如果不存在则创建"""
        if cls._instance is None:
            cls._instance = ResourceManager()
        return cls._instance

    def __init__(self):
        """初始化资源缓存字典，禁止直接实例化"""
        if ResourceManager._instance is not None:
            raise RuntimeError("Use ResourceManager.get_instance() instead")
        self._image_cache = {}
        self._icon_cache = {}

    def get_image(self, rel_path: str) -> QPixmap:
        """获取缓存的图片资源"""
        if rel_path in self._image_cache:
            return self._image_cache[rel_path]

        full_path = resource_path(rel_path)
        if not os.path.exists(full_path):
            # 可以在这里返回一个默认的空图片或者打印警告
            print(f"[ResourceManager] Warning: Image not found at {full_path}")
            return QPixmap()
            
        pixmap = QPixmap(full_path)
        # 存入缓存
        self._image_cache[rel_path] = pixmap
        return pixmap

    def get_icon(self, rel_path: str) -> QIcon:
        """获取缓存的图标资源"""
        if rel_path in self._icon_cache:
            return self._icon_cache[rel_path]

        full_path = resource_path(rel_path)
        if not os.path.exists(full_path):
            print(f"[ResourceManager] Warning: Icon not found at {full_path}")
            return QIcon()

        icon = QIcon(full_path)
        # 存入缓存
        self._icon_cache[rel_path] = icon
        return icon
