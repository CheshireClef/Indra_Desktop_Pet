# FGO因陀罗-桌面宠物 (Indra Desktop Pet)

基于游戏《Fate/Grand Order》中 Lancer 因陀罗（Indra）形象制作的互动桌面宠物。
神王大人亲自在电脑桌面上陪伴你，感激吧凡人！

> **注意**：本项目为同人作品，无盈利目的，一切版权归原版权方所有。

---

## 📖 项目简介

这是一个结合了现代 LLM（大语言模型）技术的桌面宠物程序。通过观察屏幕和搜索内置的《摩诃婆罗多》、FGO数据库，它会对屏幕的内容给出符合身份的评论，主打一个陪伴感。

### 核心特性
- **沉浸式陪伴**：透明无边框窗口，始终置顶，支持鼠标拖拽互动。
- **智能对话**：接入 DeepSeek/ChatGPT 等大模型，拥有基于 RAG（检索增强生成）构建的 FGO 与摩诃婆罗多背景知识库，还原神王大人的傲娇与威严。
- **屏幕观察**：具备“视觉”能力，能定时观察你的屏幕内容并发表评论（需配置 Vision 模型 API）。
- **本地化隐私**：除必要的 API 调用外，所有聊天记录和截图数据均存储于本地。

---

## 📂 项目结构

```
Indra_Desktop_Pet/
├── assets/             # 资源文件夹（立绘、图标、UI素材）
├── config/             # 配置文件（用户设置等）
├── docs/               # 开发文档（架构、进度、环境配置等）
├── models/             # 本地离线模型（目前包含 gte-multilingual-base 向量模型）
├── src/                # 源代码目录
│   ├── gui/            # 图形界面逻辑 (PySide6)
│   ├── llm/            # LLM 交互与 RAG 核心逻辑 (LlamaIndex)
│   ├── vision/         # 视觉模块 (屏幕截图与图像识别)
│   └── main.py         # 程序启动入口
├── .env.example        # 开发环境 API 配置模板
└── README.md           # 项目说明文档
```

> 开发者文档见 **[docs/README.md](docs/README.md)**（项目概况、技术要点、架构、进度、`.env` 配置说明等）。

---

## ✅ 功能特性进度表

### 基础交互
- [x] 桌面透明无边框窗口
- [x] 鼠标拖拽移动
- [x] 系统托盘图标与右键菜单
- [x] 气泡式对话框

### 智能系统
- [x] LLM 对话接口（支持 OpenAI 格式 API）
- [x] RAG 知识库（集成 FGO 剧情与摩诃婆罗多史诗）
- [x] 屏幕内容监视与评论（基于 Qwen-VL 等视觉模型）
- [x] 本地向量检索（Alibaba-NLP/gte-multilingual-base）

### 待开发特性 (Todo)
- [ ] 戳一戳互动动画
- [x] 根据对话情绪自动切换表情/Emoji
- [ ] 闲置待机动画（打瞌睡、随机漫游等）
- [ ] 长期记忆系统优化
- [ ] 更多游戏性功能（好感度等）

---

## 🚀 快速开始

### 1. 环境准备
- 操作系统：Windows 10/11
- Python 版本：3.10 或以上
- 必要的 API Key：
  - 推荐使用 DeepSeek 或 硅基流动 SiliconFlow
  - **SiliconFlow 邀请福利**：使用我的邀请链接注册可获赠额度同时给作者的额度回个血 [https://cloud.siliconflow.cn/i/nkM72iXr](https://cloud.siliconflow.cn/i/nkM72iXr) (邀请码: nkM72iXr)

### 2. 安装与运行
1. 克隆本项目到本地：
   ```bash
   git clone https://github.com/YourUsername/Indra_Desktop_Pet.git
   ```
2. 安装依赖库：
   请确保安装了 `PySide6`, `llama-index`, `openai` 等核心依赖（完整列表见 [docs/02-技术要点.md](docs/02-技术要点.md)）。
3. **（开发环境）** 复制 `.env.example` 为 `.env` 并填入 LLM / 视觉 API 密钥（详见 [docs/05-开发环境配置.md](docs/05-开发环境配置.md)）。
4. 运行程序：
   ```bash
   python src/main.py
   ```
……好吧其实我也可能会将打包后的程序上传到网盘，到时候直接下载解压运行里面的exe文件即可。

### 3. 初始设置
- 启动后，右键点击托盘图标或立绘，选择 **“设置”**。
- 在 **“模型设置”** 选项卡中，填入你的 LLM API URL 和 Key。
  - **聊天模型**：DeepSeek，chatgpt，都行
  - **视觉模型**：推荐 Qwen/Qwen2-VL-72B-Instruct (用于屏幕观察)
- 保存设置后，即可开始与因陀罗互动。

---

## 🛠️ 技术细节

- **UI 框架**：PySide6 (Qt for Python)
- **LLM 框架**：LlamaIndex
- **向量模型**：Alibaba-NLP/gte-multilingual-base (本地离线运行，无需联网嵌入)
- **视觉能力**：基于定期屏幕截图 + 多模态大模型 (VLM) 分析

---

## ❓ 常见问题 (FAQ)

**Q: 桌宠立绘突然消失了？**
A: 这是一个偶发 Bug。请尝试从系统托盘图标右键菜单中选择「显示桌宠」。如果无效，先点「隐藏桌宠」再点「显示桌宠」即可恢复。

**Q: 屏幕监视功能没反应？**
A: 这取决于网络状况和 API 响应速度。截图后需要一定时间生成评论。如果遇到 403 错误，请检查 API Key 额度或更换服务商。

**Q: 为什么程序体积这么大？**
A: ~~因为因陀罗神的灵基就是这么庞大~~为了实现开箱即用的 RAG 体验，项目内置了离线向量模型，数据库的嵌入式文件也已经全部在我自己的机器上生成好了。
*2026/1/19 更新：已替换为 `gte-multilingual-base`，体积从 2GB+ 优化至约 500MB。*

---

## 📄 版权与致谢

- **立绘绘制**：@废料漩涡
- **程序开发**：@柴犬面包 ~~以及她的那些个AI助手们，它们个个有情有义~~
- **开源协议**：[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) (署名-非商业性使用)

> 感谢阿里达摩院的 `gte-multilingual-base` 模型，任劳任怨的 DeepSeek api，编程之神Claude和Trae，什么问题都会努力回答的便宜大碗的豆包和GPT。还有我的ROG ALLY，它本来应该运行一些游戏，结果一个多月以来都在风扇狂转地承担一些编程工作，不得不说还挺好使！
