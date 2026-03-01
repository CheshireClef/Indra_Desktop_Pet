# 后端与数据结构说明（BACKEND_STRUCTURE）

本文档仅描述**配置结构**与**知识库（数据源）**的文件与内容约定，不涉及 LlamaIndex 向量索引、docstore、vector_store 等内部实现。

---

## 1. 配置结构：config/settings.json

配置文件由 `src/settings_manager.py` 的 `SettingsManager` 读写；缺失键会在加载时从默认值合并。以下为完整 schema（键名、类型、含义、默认值）。

### 1.1 顶层键

| 顶层键 | 类型 | 说明 |
|--------|------|------|
| `pet` | object | 桌宠外观与基础行为 |
| `behavior` | object | 交互与定时行为 |
| `user` | object | 用户侧展示用信息 |
| `llm` | object | 对话用 LLM API 配置 |
| `vision` | object | 屏幕观察用视觉 API 与行为配置 |

### 1.2 pet

| 字段 | 类型 | 含义 | 默认值 |
|------|------|------|--------|
| `name` | string | 桌宠名称（如「因陀罗」） | `"因陀罗"` |
| `scale` | number | 立绘缩放比例 | `1.0` |
| `initial_position` | string | 初始位置（如 `bottom-right`） | `"bottom-right"` |
| `font_size` | number | 聊天/气泡字体大小 | `13` |

### 1.3 behavior

| 字段 | 类型 | 含义 | 默认值 |
|------|------|------|--------|
| `idle_interval_s` | number | 闲置判定间隔（秒） | `7` |
| `screen_watch_enabled` | boolean | 是否开启屏幕观察 | `false` |
| `screen_watch_interval_s` | number | 屏幕观察触发间隔（秒） | `60` |
| `temp_bubble_duration_s` | number | 临时气泡显示时长（秒） | `8` |

### 1.4 user

| 字段 | 类型 | 含义 | 默认值 |
|------|------|------|--------|
| `display_name` | string | 用户称呼（如「主人」「御主」） | `"主人"` |

### 1.5 llm

| 字段 | 类型 | 含义 | 默认值 |
|------|------|------|--------|
| `provider` | string | 提供商标识（如 openai / deepseek / custom） | `"openai"` |
| `api_key` | string | API Key | `""` |
| `base_url` | string | API 根 URL（不含 /v1/chat/completions） | 见代码默认 |
| `model` | string | 模型名 | `"gpt-4o-mini"` |
| `temperature` | number | 采样温度 | `1.0` |
| `max_tokens` | number | 单次回复最大 token 数 | `512` |
| `history_rounds` | number | 带入历史的对话轮数 | 代码中 default 6，建议与 DEFAULTS 一致时在文档中写 6～10 |

*注：`settings_manager.DEFAULTS` 中未显式列出 `base_url`、`history_rounds`，但运行时通过 `get(..., default=...)` 使用；若 JSON 中缺失则用上述默认。*

### 1.6 vision

| 字段 | 类型 | 含义 | 默认值 |
|------|------|------|--------|
| `api_url` | string | 视觉 API 完整 URL 或根 URL | `"https://api.siliconflow.cn/v1/chat/completions"` |
| `api_key` | string | API Key | `""` |
| `enabled` | boolean | 是否启用视觉能力（与 behavior.screen_watch_enabled 配合使用） | `false` |
| `auto_interval` | number | 自动间隔（当前代码中未使用可忽略） | `0` |
| `keep_last_n_screenshots` | number | 本地保留的最近截图数量 | `3` |
| `model` | string | 视觉模型名（如 Qwen-VL） | `"Qwen/Qwen3-VL-32B-Instruct"` |

---

## 2. 知识库结构：src/llm/knowledge/

知识库分为两个数据源目录，分别对应 **lore**（设定/剧情）与 **style**（语气/风格）。程序会递归扫描子目录中的文本与约定格式的 JSON，构建向量索引（索引持久化在 `src/llm/knowledge_db/`，本处不描述其内部格式）。

### 2.1 lore（设定与剧情）

- **路径**：`src/llm/knowledge/lore/`
- **用途**：RAG 检索时提供因陀罗相关设定、摩诃婆罗多与 FGO 剧情等「事实性」内容。

#### 目录约定

- **maha_vol_01** ～ **maha_vol_06**：摩诃婆罗多分卷，每卷下为若干 `story_XXX.txt` 与同名 `story_XXX.facts.json`。
- **fgo剧情总结/**：FGO 相关剧情总结等，多为 `.txt` 与 `.facts.json` 成对或单文件。
- 其他根目录下的 `.txt` / 资料类文件（如 `阿周那的资料.txt`）也会被扫描。
- 非文本类（如 `译名对照表.yaml`）是否参与索引以当前 `knowledge_base` 实现为准（一般为按扩展名或 content 解析）。

#### 文件约定

- **原文**：`story_XXX.txt` 或任意 `.txt`，UTF-8 纯文本。
- **结构化事实**：与原文同名的 `story_XXX.facts.json`（或 `*.facts.json` / `*.facts.txt`），用于更细粒度的事件与角色检索。

#### .facts.json 单条结构（简要）

每文件为一个 JSON 数组，元素为「事件/事实」对象，常见字段包括：

| 字段 | 类型 | 说明 |
|------|------|------|
| `extraction_class` | string | 类型，如 `"event"` |
| `extraction_text` | string | 该条事实的文本描述（中/英等） |
| `attributes` | object | 可选；如 `characters`, `action`, `relationships`, `supernatural_elements` 等 |
| `char_interval` / `_token_interval` | object / null | 可选；与原文对齐信息 |

程序将整文件内容作为 Document 文本摄入，按 lore 的 chunk 配置（如 chunk_size=800, overlap=200）做分块与向量化。

### 2.2 style（语气与风格）

- **路径**：`src/llm/knowledge/style/`
- **用途**：RAG 检索时提供因陀罗的说话风格、台词示例等，用于生成口吻一致的回复。

#### 目录与文件约定

- 无强制子目录结构；当前示例为根目录下若干 `.txt`，如：
  - `因陀罗大试炼剧情.txt`
  - `Indra语音_清理完成.txt`
  - `终章剧情文本_脱水版.txt`
- 内容为剧情对话或语音文本的脱水/整理版，UTF-8 纯文本。
- style 使用较短的 chunk（如 chunk_size=300, overlap=50）以保留语气片段。

---

## 3. 与进度/实现的对应关系

- 配置的增删改以 `SettingsManager` 与设置对话框为准；新增配置项时建议同步更新本文档 schema。
- 知识库新增卷/目录或变更 `.facts.json` 格式时，需考虑索引重建（程序会根据文件变更自动或按策略重建，见 `knowledge_base.py`）。

---

*文档版本：初稿，与项目文档与进度体系配套。*
