# Indra_Desktop_Pet
基于FGO因陀罗的互动桌宠

目前还在新建文件夹阶段，等我慢慢地做……

如果看到了本项目请装作没看到，谢谢你

# FGO因陀罗桌宠开发项目进度表

## 0. 项目信息
- 项目类型：同人桌宠
- 允许：署名基础上的自由传播与修改
- 禁止：盈利用途
- LICENSE 建议：CC BY-NC（署名-非商业性）

---

## 1. 环境与工具准备
- [x] 安装 Python（3.10 或以上）
- [x] 安装 pip、venv（Python 自带）
- [x] 安装 Git（https://git-scm.com/）
- [x] 安装 VS Code
- [x] 在 VS Code 中安装 Python 插件
- [x] 在 VS Code 中安装 GitHub 扩展（可选）

---

## 2. 项目初始化
- [x] 在 GitHub 创建仓库（LICENSE 选 CC BY-NC）
- [x] 在本地 `git clone` 项目
- [x] 创建 Python 虚拟环境：`python -m venv venv`
- [x] 激活虚拟环境并安装基础依赖
---

## 3. 桌宠暂用立绘准备
- [x] 寻找一张合适的 Q 版静态立绘作为占位皮肤  
- [x] 将角色图像放入 `assets/images/pet.png`
- [x] 确认图像格式与尺寸

---

## 4. 核心功能开发
### 4.1 基础窗口（桌宠主体）
- [x] 创建透明、无边框、置顶的小窗口
- [x] 加载并显示立绘
- [x] 允许拖动角色（鼠标拖拽）
- [x] 创建系统托盘图标
- [x] 创建系统托盘右键菜单

### 4.2 行为系统（可按阶段逐步实现）
- [ ] 角色待机动画（静态 → 简单 GIF → 多帧动画）
- [ ] 角色点击反应（弹窗、语音、动作）
- [ ] 定时动作（眨眼、伸懒腰等）

### 4.3 扩展功能（可选）
- [ ] 角色对白系统（文本气泡）
- [ ] 简易菜单（右键菜单）
- [ ] 动画系统（多帧 PNG 或 sprite sheet）
- [ ] 多皮肤切换

---

## 5. 资源制作与替换
- [ ] 制作/替换成正式立绘
- [ ] 制作更多动作帧（眨眼 / 摇头 / 走动）
- [ ] 调整动画速度和透明度

---

## 6. 测试 & 优化
- [ ] 测试在 Windows 11 的桌面行为（置顶、拖动、遮挡）
- [ ] 测试资源路径、启动方式
- [ ] 优化内存占用、帧率
- [ ] 修复窗口闪烁、透明边缘等问题

---

## 7. 打包与发布
- [ ] 使用 PyInstaller 打包为 exe
- [ ] 清理无用文件
- [ ] 更新 README 文档
- [ ] 上传 Release 到 GitHub

---
备注：
听说屏幕图像识别可以用硅基流动Siliconflow.cn的大模型api做，用qwen_72B识别，生成的内容发送给deepseek处理

关于设置菜单：

把**所有可配置项统一放到一个 JSON 配置文件**里：

- 配置文件：`config/settings.json`（一份文件管理所有用户可调参数）
- 一个小工具类 `SettingsManager` 负责读写（自动处理默认值）
- 一个简单的 PySide6 `SettingsDialog` 用于在 GUI 里修改配置（从右键菜单「设置」打开）
- 把 `PetWindow` 改成接收 `SettingsManager`，并在设置变更后动态应用（例如修改 `scale` 会立即重载图片）

 配置文件：`config/settings.json`

`src/settings_manager.py`（读写 JSON，单一入口）

`src/gui/settings_dialog.py`（简单的设置窗口，便于增删项）

`src/gui/pet_window.py`：让 PetWindow 接收 `SettingsManager` 并能响应设置更改

 修改 `src/gui/tray.py`：把菜单「设置」绑定到 `pet_window.open_settings_windo`

修改 `src/main.py`：创建 SettingsManager 并把它传给 PetWindow

src/
 ├─ llm/
 │   ├─ persona.txt        # 人设 prompt（可编辑）
 │   ├─ chat_manager.py    # 对话管理（记忆裁剪）
 └─ memory/
     └─ memory.json        # 长期记忆（结构化）

对话数据结构：
[
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "..."}
]
