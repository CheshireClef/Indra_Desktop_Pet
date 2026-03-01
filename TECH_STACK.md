# 技术栈说明（TECH_STACK）

本文档列出 Indra Desktop Pet 的运行环境、依赖包、外部 API 与本地资源，便于环境复现与协作开发。项目当前**未**提供 `requirements.txt` 或 `pyproject.toml`，依赖以本文档与 README 为准。

---

## 1. 运行环境

| 项目     | 要求                |
|----------|---------------------|
| 操作系统 | Windows 10 / 11     |
| Python   | 3.10 或以上         |
| 入口     | `python src/main.py` |

---

## 2. 依赖清单

### 2.1 核心依赖（必须）

| 包名 | 用途 | 使用位置（示例） |
|------|------|------------------|
| **PySide6** | Qt for Python，GUI（窗口、托盘、设置、聊天气泡） | `main.py`, `gui/*.py` |
| **llama-index-core** | 向量索引、存储上下文、文档与节点解析 | `llm/knowledge_base.py` |
| **llama-index-embeddings-huggingface** | 本地 HuggingFace 嵌入模型封装 | `llm/knowledge_base.py` |
| **requests** | HTTP 请求（LLM API、视觉 API） | `llm/chat_manager.py`, `vision/qwen_vision.py` |
| **mss** | 跨平台屏幕截图 | `vision/screen_observer.py` |
| **Pillow (PIL)** | 图像处理（截图保存等） | `vision/screen_observer.py` |
| **transformers** | HuggingFace 模型加载（嵌入层） | 由 `llama_index.embeddings.huggingface` 间接使用 |
| **torch** | 深度学习后端，嵌入模型运行 | `llm/knowledge_base.py`（模型 to CPU） |
| **huggingface_hub** | 模型下载（若使用下载脚本） | `download_model.py` |

### 2.2 可选依赖

| 包名 | 用途 | 说明 |
|------|------|------|
| **tiktoken_ext** | OpenAI 风格 token 计数 | 在 `knowledge_base.py` 中 try/except 导入，非必须 |

### 2.3 标准库（无额外安装）

- `json`, `os`, `sys`, `copy`, `threading`, `hashlib`, `pathlib`, `typing`, `webbrowser`, `ast`, `pydoc`, `pyexpat` 等（部分为未使用或误用导入，不影响运行）。

---

## 3. 外部 API

### 3.1 LLM API（对话与屏幕评论）

- **协议**：OpenAI 兼容的 Chat Completions
- **端点**：`{base_url}/v1/chat/completions`（若用户填的 base_url 已含路径则直接使用）
- **配置项**：`llm.base_url`, `llm.api_key`, `llm.model`, `llm.temperature`, `llm.max_tokens`, `llm.history_rounds`
- **说明**：推荐 DeepSeek、SiliconFlow 等兼容该格式的服务；`llm.provider` 用于 UI 展示与部分逻辑分支（如 `custom`）。

### 3.2 视觉 API（屏幕截图描述）

- **协议**：与 LLM 相同，OpenAI 兼容多模态 Chat Completions（支持 `image_url`）
- **端点**：由 `vision.api_url` 指定（可与 LLM 不同）
- **配置项**：`vision.api_url`, `vision.api_key`, `vision.model`
- **说明**：推荐 Qwen-VL 等（如 `Qwen/Qwen3-VL-32B-Instruct`），用于将截图转为文字描述后再交给 LLM 生成评论。

---

## 4. 本地资源

| 路径 | 说明 |
|------|------|
| **models/gte-multilingual-base** | 本地嵌入模型目录，须含 `config.json`, `modeling.py`, `configuration.py` 及权重（`.bin` 或 `.safetensors`），离线 RAG 检索用 |
| **assets/** | 立绘、图标等 UI 资源 |
| **config/** | 用户配置目录，主文件为 `config/settings.json` |
| **src/llm/knowledge/** | 知识库源数据：`lore/`（设定与剧情）、`style/`（语气风格） |
| **src/llm/knowledge_db/** | LlamaIndex 持久化索引（由程序按需生成/重建，一般不手改） |
| **screenshots/** | 屏幕观察产生的截图临时目录，保留数量由 `vision.keep_last_n_screenshots` 控制 |

---

## 5. 打包与分发

- 使用 **PyInstaller** 时，项目内存在 `FGO因陀罗桌宠.spec` 等配置；资源与配置路径通过 `utils.resource_path` 在开发/打包环境下统一解析。

---

*文档版本：初稿，与项目文档与进度体系配套。*
