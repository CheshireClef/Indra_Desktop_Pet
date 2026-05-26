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
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal

from llm.clients.url_utils import chat_completions_url, normalize_base_url
from llm.providers.registry import default_base_url, load_registry

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
    # 新 schema（开发环境可选）
    "MODELS_VENDOR":   ("models", "_env_vendor"),
    "MODELS_API_KEY":  ("models", "_env_api_key"),
    "MODELS_BASE_URL": ("models", "_env_base_url"),
    "MODELS_CHAT_MODEL": ("models", "_env_chat_model"),
    "MODELS_VISION_MODEL": ("models", "_env_vision_model"),
    "MODELS_VISION_VENDOR": ("models", "_env_vision_vendor"),
    "MODELS_VISION_API_KEY": ("models", "_env_vision_api_key"),
    "MODELS_VISION_BASE_URL": ("models", "_env_vision_base_url"),
    "MODELS_SAME_CONNECTION_AS_CHAT": ("models", "_env_same_connection"),
}

# models v2 默认块（单一真相源）
MODELS_DEFAULTS: Dict[str, Any] = {
    "schema_version": 2,
    "connections": [
        {
            "id": "default",
            "vendor": "siliconflow",
            "protocol": "openai_compatible",
            "base_url": "https://api.siliconflow.cn/v1",
            "api_key": "",
        }
    ],
    "chat": {
        "connection_id": "default",
        "model": "",
        "temperature": 1.0,
        "max_tokens": 512,
        "history_rounds": 10,
        "output_mode": "auto",
    },
    "vision": {
        "same_connection_as_chat": True,
        "connection_id": "default",
        "model": "Qwen/Qwen3-VL-32B-Instruct",
    },
    "capabilities_cache": {},
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
        "model": "Qwen/Qwen3-VL-32B-Instruct",
        "enabled": False,
        "auto_interval": 0,
        "keep_last_n_screenshots": 3,
    },
    "models": copy.deepcopy(MODELS_DEFAULTS),
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
        self._migrate_models_v2()
        self._sync_legacy_from_models()
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

    def get_models_block(self) -> Dict[str, Any]:
        if "models" not in self._data or not isinstance(self._data["models"], dict):
            self._data["models"] = copy.deepcopy(MODELS_DEFAULTS)
        return self._data["models"]

    def _infer_vendor_from_url(self, url: str) -> str:
        host = (urlparse(url or "").netloc or "").lower()
        mapping = {
            "siliconflow": "siliconflow",
            "deepseek": "deepseek",
            "openai": "openai",
            "openrouter": "openrouter",
            "bigmodel": "zhipu",
            "dashscope": "qwen",
            "moonshot": "moonshot",
            "mistral": "mistral",
            "groq": "groq",
            "minimax": "minimax",
        }
        for key, vendor in mapping.items():
            if key in host:
                return vendor
        if "11434" in url or "ollama" in host:
            return "ollama"
        if "1234" in url:
            return "lmstudio"
        if ":8000" in url:
            return "vllm"
        return "custom_openai"

    def _migrate_models_v2(self):
        """从旧 llm/vision 迁移到 models v2（幂等）。"""
        models = self.get_models_block()
        if models.get("schema_version") == 2 and models.get("_migrated_from_v1"):
            return
        if models.get("schema_version") == 2 and self._data.get("llm") and models.get("chat", {}).get("model"):
            models["_migrated_from_v1"] = True
            return

        llm = self._data.get("llm") or {}
        vision = self._data.get("vision") or {}
        provider = (llm.get("provider") or "deepseek").lower()
        vendor = provider if provider in load_registry() else self._infer_vendor_from_url(
            llm.get("base_url") or ""
        )
        if vendor not in load_registry():
            vendor = "custom_openai"

        llm_base = normalize_base_url(llm.get("base_url") or default_base_url(vendor))
        vision_raw = vision.get("api_url") or ""
        vision_base = normalize_base_url(vision_raw or llm_base or default_base_url("siliconflow"))

        llm_key = llm.get("api_key") or ""
        vision_key = vision.get("api_key") or llm_key
        same_conn = normalize_base_url(vision_raw or "") == normalize_base_url(llm_base) or not vision_key or vision_key == llm_key

        conn = {
            "id": "default",
            "vendor": vendor,
            "protocol": "openai_compatible",
            "base_url": llm_base or vision_base,
            "api_key": llm_key or vision_key,
        }
        connections = [conn]
        vision_conn_id = "default"
        if not same_conn:
            v_vendor = self._infer_vendor_from_url(vision_raw) if vision_raw else vendor
            if v_vendor not in load_registry():
                v_vendor = "custom_openai"
            connections.append({
                "id": "vision",
                "vendor": v_vendor,
                "protocol": "openai_compatible",
                "base_url": vision_base,
                "api_key": vision_key,
            })
            vision_conn_id = "vision"
        models["schema_version"] = 2
        models["connections"] = connections
        models["chat"] = {
            "connection_id": "default",
            "model": llm.get("model") or "",
            "temperature": float(llm.get("temperature", 1.0)),
            "max_tokens": int(llm.get("max_tokens", 512)),
            "history_rounds": int(llm.get("history_rounds", 10)),
            "output_mode": "auto",
        }
        models["vision"] = {
            "same_connection_as_chat": same_conn,
            "connection_id": vision_conn_id,
            "model": vision.get("model") or "Qwen/Qwen3-VL-32B-Instruct",
        }
        if "capabilities_cache" not in models:
            models["capabilities_cache"] = {}
        models["_migrated_from_v1"] = True
        print("[SettingsManager] 已迁移 models v2 配置")

    def _sync_legacy_from_models(self):
        """将 models 投影到旧 llm/vision 键，兼容旧 UI 与未迁移调用方。"""
        models = self.get_models_block()
        chat_b = self.get_chat_binding()
        vision_b = self.get_vision_binding()
        vendor = chat_b.get("vendor", "custom_openai")
        legacy_provider = vendor if vendor in ("deepseek", "openai") else "custom"

        self._data.setdefault("llm", {})
        self._data["llm"].update({
            "provider": legacy_provider,
            "api_key": chat_b.get("api_key") or "",
            "base_url": chat_b.get("base_url") or "",
            "model": chat_b.get("model") or "",
            "temperature": chat_b.get("temperature", 1.0),
            "max_tokens": chat_b.get("max_tokens", 512),
            "history_rounds": chat_b.get("history_rounds", 10),
        })
        self._data.setdefault("vision", {})
        self._data["vision"].update({
            "api_url": chat_completions_url(vision_b.get("base_url") or ""),
            "api_key": vision_b.get("api_key") or "",
            "model": vision_b.get("model") or "",
        })

    @staticmethod
    def _env_get(name: str) -> Optional[str]:
        """读取非空环境变量；空字符串视为未设置。"""
        raw = os.environ.get(name)
        if raw is None:
            return None
        s = str(raw).strip()
        return s if s else None

    @staticmethod
    def _env_bool_optional(name: str) -> Optional[bool]:
        raw = SettingsManager._env_get(name)
        if raw is None:
            return None
        return raw.lower() in ("1", "true", "yes", "on")

    def _find_or_create_connection(self, models: Dict[str, Any], conn_id: str) -> Dict[str, Any]:
        conn_list = models.setdefault("connections", copy.deepcopy(MODELS_DEFAULTS["connections"]))
        for c in conn_list:
            if isinstance(c, dict) and c.get("id") == conn_id:
                return c
        conn = {
            "id": conn_id,
            "vendor": "custom_openai",
            "protocol": "openai_compatible",
            "base_url": "",
            "api_key": "",
        }
        conn_list.append(conn)
        return conn

    def _resolve_vendor_id(self, vendor_raw: str, base_url: str = "") -> str:
        v = (vendor_raw or "").lower()
        if v in load_registry():
            return v
        if base_url:
            inferred = self._infer_vendor_from_url(base_url)
            if inferred in load_registry():
                return inferred
        return "custom_openai"

    def _apply_env_to_models(self) -> bool:
        """
        开发环境：将 .env 中的 MODELS_* / LLM_* / VISION_* 注入内存中的 models 块。
        不写入 settings.json，避免密钥落盘。
        """
        if not _IS_DEV:
            return False

        chat_vendor_env = self._env_get("MODELS_VENDOR") or self._env_get("LLM_PROVIDER")
        chat_key_env = self._env_get("MODELS_API_KEY") or self._env_get("LLM_API_KEY")
        chat_base_env = self._env_get("MODELS_BASE_URL") or self._env_get("LLM_BASE_URL")
        chat_model_env = self._env_get("MODELS_CHAT_MODEL") or self._env_get("LLM_MODEL")
        vision_model_env = self._env_get("MODELS_VISION_MODEL") or self._env_get("VISION_MODEL")
        vision_vendor_env = self._env_get("MODELS_VISION_VENDOR")
        vision_key_env = self._env_get("MODELS_VISION_API_KEY") or self._env_get("VISION_API_KEY")
        vision_base_env = self._env_get("MODELS_VISION_BASE_URL") or self._env_get("VISION_API_URL")
        same_conn_env = self._env_bool_optional("MODELS_SAME_CONNECTION_AS_CHAT")

        has_any = any(
            (
                chat_vendor_env,
                chat_key_env,
                chat_base_env,
                chat_model_env,
                vision_model_env,
                vision_vendor_env,
                vision_key_env,
                vision_base_env,
                same_conn_env is not None,
            )
        )
        if not has_any:
            return False

        models = self.get_models_block()
        chat_conn = self._find_or_create_connection(models, "default")
        touched = False

        if chat_vendor_env:
            chat_conn["vendor"] = self._resolve_vendor_id(chat_vendor_env, chat_conn.get("base_url") or "")
            touched = True
        if chat_key_env is not None:
            chat_conn["api_key"] = chat_key_env
            touched = True
        if chat_base_env:
            chat_conn["base_url"] = normalize_base_url(chat_base_env)
            touched = True
            if not self._env_get("MODELS_VENDOR") and not self._env_get("LLM_PROVIDER"):
                chat_conn["vendor"] = self._infer_vendor_from_url(chat_base_env)
        if chat_model_env:
            models.setdefault("chat", {})["model"] = chat_model_env
            touched = True

        vision_cfg = models.setdefault("vision", {})
        if vision_model_env:
            vision_cfg["model"] = vision_model_env
            touched = True

        has_vision_conn_env = any((vision_vendor_env, vision_key_env, vision_base_env))
        same_conn = same_conn_env
        if same_conn is None and has_vision_conn_env:
            chat_base = normalize_base_url(chat_conn.get("base_url") or "")
            vision_base = normalize_base_url(vision_base_env) if vision_base_env else chat_base
            chat_key_val = chat_conn.get("api_key") or ""
            differs = False
            if vision_key_env is not None and vision_key_env != chat_key_val:
                differs = True
            if vision_base_env and vision_base != chat_base:
                differs = True
            if vision_vendor_env:
                vv = self._resolve_vendor_id(
                    vision_vendor_env, vision_base_env or chat_conn.get("base_url") or ""
                )
                if vv != (chat_conn.get("vendor") or "custom_openai"):
                    differs = True
            same_conn = not differs

        if same_conn is True:
            vision_cfg["same_connection_as_chat"] = True
            vision_cfg["connection_id"] = "default"
            touched = True
        elif same_conn is False or has_vision_conn_env:
            vision_conn = self._find_or_create_connection(models, "vision")
            if vision_vendor_env:
                vision_conn["vendor"] = self._resolve_vendor_id(
                    vision_vendor_env, vision_conn.get("base_url") or ""
                )
                touched = True
            if vision_key_env is not None:
                vision_conn["api_key"] = vision_key_env
                touched = True
            if vision_base_env:
                vision_conn["base_url"] = normalize_base_url(vision_base_env)
                touched = True
                if not vision_vendor_env:
                    vision_conn["vendor"] = self._infer_vendor_from_url(vision_base_env)
            if same_conn is False or has_vision_conn_env:
                vision_cfg["same_connection_as_chat"] = False
                vision_cfg["connection_id"] = "vision"
                touched = True

        return touched

    def get_chat_binding(self) -> Dict[str, Any]:
        self._apply_env_to_models()
        models = self.get_models_block()
        chat = models.get("chat") or {}
        conn_id = chat.get("connection_id", "default")
        conn = next(
            (c for c in (models.get("connections") or []) if c.get("id") == conn_id),
            (models.get("connections") or [{}])[0] if models.get("connections") else {},
        )
        return {
            "connection_id": conn_id,
            "vendor": conn.get("vendor", "custom_openai"),
            "base_url": conn.get("base_url") or "",
            "api_key": conn.get("api_key") or "",
            "model": chat.get("model") or "",
            "temperature": float(chat.get("temperature", 1.0)),
            "max_tokens": int(chat.get("max_tokens", 512)),
            "history_rounds": int(chat.get("history_rounds", 10)),
            "output_mode": chat.get("output_mode", "auto"),
        }

    def get_vision_binding(self) -> Dict[str, Any]:
        self._apply_env_to_models()
        models = self.get_models_block()
        vision = models.get("vision") or {}
        if vision.get("same_connection_as_chat", True):
            b = dict(self.get_chat_binding())
            b["model"] = vision.get("model") or b.get("model") or "Qwen/Qwen3-VL-32B-Instruct"
            return b
        conn_id = vision.get("connection_id", "default")
        conn = next(
            (c for c in (models.get("connections") or []) if c.get("id") == conn_id),
            {},
        )
        return {
            "connection_id": conn_id,
            "vendor": conn.get("vendor", "custom_openai"),
            "base_url": conn.get("base_url") or "",
            "api_key": conn.get("api_key") or "",
            "model": vision.get("model") or "Qwen/Qwen3-VL-32B-Instruct",
            "same_connection_as_chat": False,
        }

    def get_capability_cache(self, connection_id: str, model_id: str) -> Optional[Dict[str, Any]]:
        key = f"{connection_id}:{model_id}"
        cache = self.get_models_block().get("capabilities_cache") or {}
        return cache.get(key)

    def set_capability_cache(self, connection_id: str, model_id: str, data: Dict[str, Any], save_now: bool = True):
        models = self.get_models_block()
        cache = models.setdefault("capabilities_cache", {})
        cache[f"{connection_id}:{model_id}"] = data
        if save_now:
            self.save()

    def _get_legacy_projected(self, section: str, key: str, default: Any) -> Any:
        if section == "llm":
            b = self.get_chat_binding()
            m = {
                "api_key": b.get("api_key"),
                "base_url": b.get("base_url"),
                "model": b.get("model"),
                "temperature": b.get("temperature"),
                "max_tokens": b.get("max_tokens"),
                "history_rounds": b.get("history_rounds"),
                "provider": b.get("vendor") if b.get("vendor") in ("deepseek", "openai") else "custom",
            }
            return m.get(key, default)
        if section == "vision":
            b = self.get_vision_binding()
            m = {
                "api_key": b.get("api_key"),
                "api_url": chat_completions_url(b.get("base_url") or ""),
                "model": b.get("model"),
            }
            return m.get(key, default)
        return default

    def _sync_models_from_legacy_set(self, section: str, key: str, value: Any):
        models = self.get_models_block()
        if section == "llm":
            chat = models.setdefault("chat", {})
            conn_list = models.setdefault("connections", copy.deepcopy(MODELS_DEFAULTS["connections"]))
            conn = conn_list[0] if conn_list else {}
            if key == "api_key":
                conn["api_key"] = value
            elif key == "base_url":
                conn["base_url"] = normalize_base_url(str(value))
            elif key == "model":
                chat["model"] = value
            elif key == "provider":
                v = str(value).lower()
                conn["vendor"] = v if v in load_registry() else "custom_openai"
            elif key == "temperature":
                chat["temperature"] = value
            elif key == "max_tokens":
                chat["max_tokens"] = value
            elif key == "history_rounds":
                chat["history_rounds"] = value
        elif section == "vision":
            vision = models.setdefault("vision", {})
            conn_list = models.setdefault("connections", copy.deepcopy(MODELS_DEFAULTS["connections"]))
            conn = conn_list[0] if conn_list else {}
            if key == "api_key":
                conn["api_key"] = value
                vision["same_connection_as_chat"] = True
            elif key == "api_url":
                conn["base_url"] = normalize_base_url(str(value))
                vision["same_connection_as_chat"] = True
            elif key == "model":
                vision["model"] = value

    def get(self, *keys, default=None):
        """
        安全的获取配置项
        用法: sm.get("llm", "api_key", default="")

        优先级（开发环境）：
          1. 环境变量（来自 .env 文件，仅开发环境生效）
          2. settings.json 中的值（llm/vision 从 models 投影）
          3. default 参数

        打包环境下直接走 settings.json，行为与原版本一致。
        """
        self._apply_env_to_models()

        # llm/vision 从 models 投影（单一真相源）
        if len(keys) == 2 and keys[0] in ("llm", "vision"):
            if _IS_DEV:
                for env_var, mapped_keys in _ENV_KEY_MAP.items():
                    if mapped_keys == keys:
                        env_val = os.environ.get(env_var)
                        if env_val:
                            return env_val
                        break
            projected = self._get_legacy_projected(keys[0], keys[1], default)
            if projected is not None and projected != "":
                return projected
            if keys[1] in ("api_key", "model", "base_url", "api_url", "provider", "temperature", "max_tokens", "history_rounds"):
                return projected if projected is not None else default

        # 开发环境：先查环境变量映射表
        if _IS_DEV and len(keys) == 2:
            for env_var, mapped_keys in _ENV_KEY_MAP.items():
                if mapped_keys == keys:
                    env_val = os.environ.get(env_var)
                    if env_val:
                        return env_val
                    break

        d = self._data
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    def set(self, *keys, value, save_now=True):
        if len(keys) >= 2 and keys[0] in ("llm", "vision"):
            self._sync_models_from_legacy_set(keys[0], keys[1], value)

        d = self._data
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value

        if keys and keys[0] == "models":
            self._sync_legacy_from_models()
            try:
                from llm.model_service import ModelService
                ModelService.reset_cache()
            except Exception:
                pass

        if save_now:
            self.save()