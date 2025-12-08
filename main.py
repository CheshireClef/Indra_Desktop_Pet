print("=" * 50)
print("Indra 桌面宠物 v0.1")
print("=" * 50)

# 1. 检查依赖
print("\n[步骤1] 检查依赖...")
try:
    import yaml
    print("✅ PyYAML 已安装")
except ImportError:
    print("❌ PyYAML 未安装，请运行: pip install PyYAML")
    input("按Enter键退出...")
    exit(1)

try:
    from PIL import Image
    print("✅ Pillow 已安装")
except ImportError:
    print("❌ Pillow 未安装，请运行: pip install Pillow")
    input("按Enter键退出...")
    exit(1)

# 2. 读取配置
print("\n[步骤2] 读取配置文件...")
try:
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    pet_name = config['pet']['name']
    print(f"✅ 配置读取成功，宠物名字: {pet_name}")
except FileNotFoundError:
    print("⚠️  配置文件不存在，使用默认配置")
    config = {'pet': {'name': '小深'}}
    pet_name = '小深'
except Exception as e:
    print(f"❌ 读取配置失败: {e}")
    config = {'pet': {'name': '小深'}}
    pet_name = '小深'

# 3. 创建宠物窗口
print("\n[步骤3] 创建宠物窗口...")
try:
    from ui.pet_window import PetWindow
    
    print(f"创建宠物: {pet_name}")
    pet = PetWindow()
    
    print("\n" + "=" * 50)
    print("✅ 宠物创建成功！")
    print("📌 操作说明:")
    print("  1. 窗口会出现在屏幕右上角")
    print("  2. 点击立绘")
    print("  3. 宠物会向右下角移动")
    print("  4. 要关闭程序:")
    print("     - 按 Ctrl+C 在终端")
    print("     - 或用任务管理器")
    print("=" * 50 + "\n")
    
    # 启动宠物
    pet.run()
    
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保文件结构正确")
    input("按Enter键退出...")
except Exception as e:
    print(f"❌ 创建窗口失败: {e}")
    import traceback
    traceback.print_exc()
    input("按Enter键退出...")

# 4. 创建系统托盘
print("\n[步骤4] 创建系统托盘...")
try:
    from ui.system_tray import SystemTray
    
    tray = SystemTray(pet_window)
    print("✅ 系统托盘创建成功")
    
except Exception as e:
    print(f"❌ 创建系统托盘失败: {e}")
    print("将仅使用宠物窗口")
    
    print("\n" + "=" * 50)
    print("🎮 宠物已就绪！")
    print("📌 操作指南:")
    print("  1. 点击宠物: 戳一戳互动")
    print("  2. 按住拖动: 移动宠物位置")
    print("  3. 关闭方法: 任务管理器")
    print("=" * 50 + "\n")
    
    # 如果没有托盘，直接运行宠物窗口
    pet_window.run()
    exit(0)

# 5. 启动程序
print("\n" + "=" * 50)
print("🚀 程序启动完成！")
print("📌 使用说明:")
print("  1. 宠物窗口: 点击拖动互动")
print("  2. 系统托盘: 在任务栏右键图标")
print("  3. 托盘菜单:")
print("     • 显示/隐藏宠物")
print("     • 戳一戳宠物")
print("     • 移动到中心")
print("     • 退出程序")
print("=" * 50 + "\n")

# 注意：Tkinter不能在不同线程中运行GUI
# 我们需要在单独的线程中运行宠物窗口
import threading

def run_pet_window():
    pet_window.run()

# 在新线程中运行宠物窗口
pet_thread = threading.Thread(target=run_pet_window, daemon=True)
pet_thread.start()

# 在主线程中运行系统托盘（Tkinter要求主线程）
tray.run()