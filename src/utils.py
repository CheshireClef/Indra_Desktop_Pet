# src/utils.py
import os

def resource_path(rel_path: str) -> str:
    """
    统一资源路径处理：从src目录向上回溯到工程根目录，拼接相对路径
    """
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base, rel_path)