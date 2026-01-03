# src/settings_manager.py
import json
import os
import copy
from typing import Any, Dict

DEFAULTS = {
    "pet": {
        "name": "因陀罗",
        "scale": 1.0,
        "initial_position": "bottom-right"
    },
    "behavior": {
        "idle_interval_s": 7,
        "screen_watch_enabled": False,
        "screen_watch_interval_s": 60
    },
    "user": {
        "display_name": "主人"
    },
    "llm": {
        "provider": "openai",
        "api_key": "",
        "model": "gpt-4o-mini",
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


class SettingsManager:
    def __init__(self, path: str):
        self.path = path
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self._data = copy.deepcopy(DEFAULTS)
            self.save()
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            # 重要：不覆盖，先备份
            backup = self.path + ".broken"
            try:
                os.rename(self.path, backup)
            except Exception:
                pass
            self._data = copy.deepcopy(DEFAULTS)
            self.save()
            return

        self._merge_defaults(DEFAULTS, self._data)
        self.save()

    def _merge_defaults(self, defaults, target):
        for k, v in defaults.items():
            if k not in target:
                target[k] = copy.deepcopy(v)
            elif isinstance(v, dict) and isinstance(target.get(k), dict):
                self._merge_defaults(v, target[k])

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, *keys, default=None):
        d = self._data
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    def set(self, *keys, value):
        d = self._data
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value
        self.save()