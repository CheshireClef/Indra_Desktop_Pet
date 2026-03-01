# 实现计划（IMPLEMENTATION_PLAN）

本文档按「构建序列/开发步骤」组织，便于新人上手或复盘开发顺序。每条包含步骤说明、主要涉及文件/模块及简要说明。

---

## 阶段一：环境与依赖

| 步骤 | 内容 | 主要涉及 | 说明 |
|------|------|----------|------|
| 1.1 | 安装 Python 3.10+ 与创建虚拟环境 | - | Windows 10/11 推荐使用 venv 或 conda |
| 1.2 | 安装核心依赖 | 见 TECH_STACK.md | PySide6、llama-index、requests、mss、Pillow、transformers、torch、huggingface_hub 等；项目暂无 requirements.txt，以 TECH_STACK 为准 |
| 1.3 | 准备本地嵌入模型 | `models/gte-multilingual-base` | 可通过 `download_model.py` 或手动放置，须含 config + 权重 |
| 1.4 | 准备资源与配置 | `assets/`, `config/` | 首次运行可无 config，程序会写默认 settings.json |

---

## 阶段二：配置与启动

| 步骤 | 内容 | 主要涉及 | 说明 |
|------|------|----------|------|
| 2.1 | 实现配置加载与保存 | `src/settings_manager.py` | 单例 SettingsManager，DEFAULTS 合并、损坏备份、settings_changed 信号 |
| 2.2 | 程序入口与启动流程 | `src/main.py` | QApplication、启动图、SettingsManager 初始化、PetWindow + AppTray、事件循环 |
| 2.3 | 资源路径解析 | `src/utils.py` | resource_path 等，兼容开发与 PyInstaller 打包 |

---

## 阶段三：桌宠 UI 与托盘

| 步骤 | 内容 | 主要涉及 | 说明 |
|------|------|----------|------|
| 3.1 | 桌宠主窗口 | `src/gui/pet_window.py` | 无边框、透明、置顶、拖拽、缩放、与设置/聊天/屏幕观察衔接 |
| 3.2 | 立绘与动画驱动 | `src/gui/animation.py` | 帧序列、idle 等动画，与 pet_window 联动 |
| 3.3 | 系统托盘与菜单 | `src/gui/tray.py` | 托盘图标、显示/隐藏、设置、退出等 |
| 3.4 | 设置对话框 | `src/gui/settings_dialog.py` | 多标签（基础/模型），读写 SettingsManager，保存后热更新 |

---

## 阶段四：聊天与 LLM

| 步骤 | 内容 | 主要涉及 | 说明 |
|------|------|----------|------|
| 4.1 | 聊天气泡 UI | `src/gui/chat_bubble.py` | 独立悬浮窗、输入框、只读历史区、与 PetWindow/ChatManager 联动 |
| 4.2 | 对话逻辑与 API 调用 | `src/llm/chat_manager.py` | 人设构建、历史轮数、消息组装、OpenAI 兼容 POST /v1/chat/completions |
| 4.3 | 情绪标签与表情 | `src/gui/chat_bubble.py`, `src/gui/pet_window.py` | 根据回复解析情绪并驱动立绘表情/Emoji |

---

## 阶段五：知识库与 RAG

| 步骤 | 内容 | 主要涉及 | 说明 |
|------|------|----------|------|
| 5.1 | 知识库数据源 | `src/llm/knowledge/lore`, `src/llm/knowledge/style` | 目录与文件约定见 BACKEND_STRUCTURE.md |
| 5.2 | 索引加载与构建 | `src/llm/knowledge_base.py` | 本地 HuggingFaceEmbedding、lore/style 双索引、file_manifest 与增量/重建逻辑 |
| 5.3 | 检索与对话集成 | `src/llm/chat_manager.py` | 用户消息与屏幕描述触发 retrieve，结果注入 LLM 上下文 |

---

## 阶段六：屏幕观察与视觉 API

| 步骤 | 内容 | 主要涉及 | 说明 |
|------|------|----------|------|
| 6.1 | 屏幕截图 | `src/vision/screen_observer.py` | mss 全屏截图、保存到 screenshots/、按 keep_last_n 清理 |
| 6.2 | 视觉模型调用 | `src/vision/qwen_vision.py` | 截图 Base64、OpenAI 兼容多模态 API、返回描述文本 |
| 6.3 | 定时与工作线程 | `src/gui/pet_window.py`, `src/workers/screen_observer_worker.py` | screen_watch_timer、ScreenObserveWorker：截图 → 描述 → 带 tag 评论 → 临时气泡展示 |

---

## 阶段七：可选后续（按 PRD/Todo 迭代）

| 步骤 | 内容 | 主要涉及 | 说明 |
|------|------|----------|------|
| 7.1 | 戳一戳互动动画 | `src/gui/pet_window.py`, `src/gui/animation.py` | 点击/戳动事件触发专用动画 |
| 7.2 | 闲置待机动画 | `src/gui/animation.py`, `src/gui/pet_window.py` | 打瞌睡、随机漫游等，与 idle_interval_s 配合 |
| 7.3 | 长期记忆优化 | `src/llm/`（新或扩展现有） | 跨会话或长对话记忆与引用，设计待定 |
| 7.4 | 好感度等游戏性 | 待定 | 与互动行为挂钩的数值/成就，见 PRD 未来想法 |
| 7.5 | 可选持久化 | 新模块 + config 或本地 DB/文件 | 聊天记录、截图/评论是否保存及格式，见 PRD 可选持久化需求 |

---

## 文档与进度维护

- 实现过程中重要节点可在 `progress.txt` 的「已完成」中补充日期或备注。
- 新功能或想法先更新 PRD（含「未来想法」/「可选持久化」），再在本文档阶段七或新阶段中增加对应步骤，并在 progress.txt「接下来」中体现。

---

*文档版本：初稿，与项目文档与进度体系配套。*
