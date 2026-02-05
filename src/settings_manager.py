# src/settings_manager.py
"""
设置管理器模块
负责加载、保存和管理应用程序的配置信息 (settings.json)，支持默认配置回退和热更新信号。
"""
import json
import os
import copy
from typing import Any, Dict
from PySide6.QtCore import QObject, Signal

DEFAULTS = {
    "pet": {
        "name": "因陀罗",
        "scale": 1.0,
        "initial_position": "bottom-right"
    },
    "behavior": {
        "idle_interval_s": 7,
        "screen_watch_enabled": False,
        "screen_watch_interval_s": 60,
        "temp_bubble_duration_s": 8  # 新增：临时气泡默认时长10秒
    },
    "user": {
        "display_name": "主人"
    },
    "llm": {
        "provider": "openai",
        "api_key": "",
        "model": "gpt-4o-mini",
        "temperature": 1.0,  # 默认 temperature
        "max_tokens": 512
    },
    "vision": {
        "api_url": "https://api.siliconflow.cn/v1/chat/completions",
        "api_key": "",
        "enabled": False,
        "auto_interval": 0,
        "keep_last_n_screenshots": 3
    }
}


class SettingsManager(QObject):
    """
    设置管理器类 (单例模式)
    继承自 QObject 以支持信号机制 (settings_changed)
    """
    _instance = None
    # 当配置发生变化并保存时发出此信号
    settings_changed = Signal()

    def __init__(self, path: str = None):
        super().__init__()
        if path:
            self.path = path
            self._data: Dict[str, Any] = {}
            self.load()
            SettingsManager._instance = self

    @classmethod
    def get_instance(cls):
        """获取全局单例"""
        return cls._instance

    def load(self):
        """从文件加载配置，如果文件不存在或损坏则使用默认配置"""
        if not os.path.exists(self.path):
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self._data = copy.deepcopy(DEFAULTS)
            self.save()
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            # 重要：不覆盖，先备份损坏的配置文件，避免用户数据丢失
            backup = self.path + ".broken"
            try:
                os.rename(self.path, backup)
            except Exception:
                pass
            self._data = copy.deepcopy(DEFAULTS)
            self.save()
            return

        # 确保加载的配置包含所有默认字段（应对版本升级新增配置项的情况）
        self._merge_defaults(DEFAULTS, self._data)
        self.save()

    def _merge_defaults(self, defaults, target):
        """递归合并默认配置到目标配置中，补充缺失的键"""
        for k, v in defaults.items():
            if k not in target:
                target[k] = copy.deepcopy(v)
            elif isinstance(v, dict) and isinstance(target.get(k), dict):
                self._merge_defaults(v, target[k])

    def save(self):
        """保存配置到文件，并发送变更信号"""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        self.settings_changed.emit()

    def get(self, *keys, default=None):
        """
        安全的获取配置项
        用法: sm.get("llm", "api_key", default="")
        """
        d = self._data
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    def set(self, *keys, value, save_now=True):
        d = self._data
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value
        if save_now:
            self.save()