# src/settings_manager.py
"""
设置管理器模块
负责加载、保存和管理应用程序的配置信息 (settings.json)，支持默认配置回退和热更新信号。

开发环境安全说明：
  - 未打包（开发环境）时，程序会优先从项目根目录的 .env 文件读取 LLM/视觉 API 密钥等敏感配置。
  - .env 文件已加入 .gitignore，不会上传到 GitHub，避免密钥泄漏。
  - 打包后的程序（sys.frozen=True）不读取 .env，所有配置均来自 settings.json，行为与现有版本完全一致。
"""
import json
import os
import sys
import copy
from typing import Any, Dict
from PySide6.QtCore import QObject, Signal

# ========== 开发环境检测 ==========
# getattr 兼容未打包时 sys 没有 frozen 属性的情况
_IS_DEV = not getattr(sys, "frozen", False)

if _IS_DEV:
    # 开发环境下尝试加载项目根目录的 .env 文件
    try:
        from dotenv import load_dotenv
        # 计算项目根目录（src/ 的上一级）
        _root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _env_path = os.path.join(_root_dir, ".env")
        if os.path.exists(_env_path):
            load_dotenv(_env_path)
            print(f"[SettingsManager] 开发环境：已从 {_env_path} 加载 .env 配置")
        else:
            print("[SettingsManager] 开发环境：未找到 .env 文件，将使用 settings.json 中的配置")
    except ImportError:
        # 未安装 python-dotenv 时静默跳过，不影响打包版运行
        print("[SettingsManager] 开发环境：未安装 python-dotenv，跳过 .env 加载")

# ========== 环境变量 → settings 键路径 的映射 ==========
# 格式：环境变量名 -> (settings 顶层键, 子键)
# 只映射敏感/常变的字段；非敏感配置（如 model、temperature）仍从 settings.json 读取
_ENV_KEY_MAP: Dict[str, tuple] = {
    # LLM 相关
    "LLM_PROVIDER":   ("llm", "provider"),
    "LLM_API_KEY":    ("llm", "api_key"),
    "LLM_BASE_URL":   ("llm", "base_url"),
    "LLM_MODEL":      ("llm", "model"),
    # 视觉 API 相关
    "VISION_API_URL": ("vision", "api_url"),
    "VISION_API_KEY": ("vision", "api_key"),
    "VISION_MODEL":   ("vision", "model"),
}

DEFAULTS = {
    "pet": {
        "name": "因陀罗",
        "scale": 1.0,
        "initial_position": "bottom-right",
        "font_size": 13  # 新增：字体大小
    },
    "behavior": {
        "idle_interval_s": 7,
        "screen_watch_enabled": False,
        "screen_watch_interval_s": 60,
        "temp_bubble_duration_s": 8,
        "long_term_memory_enabled": False  # 长期记忆开关，默认关闭
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

        优先级（开发环境）：
          1. 环境变量（来自 .env 文件，仅开发环境生效）
          2. settings.json 中的值
          3. default 参数

        打包环境下直接走 settings.json，行为与原版本一致。
        """
        # 开发环境：先查环境变量映射表，有值则优先返回
        if _IS_DEV and len(keys) == 2:
            for env_var, mapped_keys in _ENV_KEY_MAP.items():
                if mapped_keys == keys:
                    env_val = os.environ.get(env_var)
                    if env_val:  # 非空才覆盖，空字符串视为"未配置"
                        return env_val
                    break

        # 从 settings.json 数据中读取
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