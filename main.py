print("=" * 50)
print("Indra 桌面宠物 v0.3")
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
    pet_window = PetWindow(config)
    
    print("✅ 宠物窗口创建成功")
    
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保文件结构正确")
    input("按Enter键退出...")
    exit(1)
except Exception as e:
    print(f"❌ 创建窗口失败: {e}")
    import traceback
    traceback.print_exc()
    input("按Enter键退出...")
    exit(1)

# 4. 创建系统托盘
print("\n[步骤4] 创建系统托盘...")
system_tray = None  # 先初始化为None
try:
    from ui.system_tray import AdvancedTray
    
    system_tray = AdvancedTray(pet_window)
    print("✅ 系统托盘创建成功")
    
    # 在后台启动托盘
    system_tray.run_in_background()
    
except ImportError as e:
    print(f"⚠️  未找到系统托盘模块: {e}")
    print("系统托盘功能将不可用")
except Exception as e:
    print(f"⚠️  创建系统托盘失败: {e}")
    print("将继续运行，但没有系统托盘功能")

# 5. 创建右键菜单
print("\n[步骤5] 创建右键菜单...")
context_menu = None  # 先初始化为None
try:
    from ui.context_menu import ContextMenu
    
    context_menu = ContextMenu(pet_window, system_tray)
    print("✅ 右键菜单创建成功")
    
    # 将系统托盘的状态同步到右键菜单
    if system_tray:
        context_menu.is_visible = system_tray.is_visible
    
except ImportError as e:
    print(f"❌ 导入右键菜单模块失败: {e}")
    print("右键菜单功能将不可用")
except Exception as e:
    print(f"❌ 创建右键菜单失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 50)
print("🚀 程序启动完成！")
print("📌 使用说明:")
print("  1. 左键点击宠物: 戳一戳互动")
print("  2. 右键点击宠物: 显示控制菜单")
print("  3. 按住左键拖动: 移动宠物位置")
print("  4. 系统托盘: 在任务栏右键图标")
print("  5. 关闭方法: 右键菜单或系统托盘")
print("=" * 50 + "\n")

# 6. 运行宠物窗口的主循环
try:
    pet_window.run()
except KeyboardInterrupt:
    print("\n检测到Ctrl+C，正在退出程序...")
    if system_tray:
        system_tray.quit_program(None, None)
    else:
        pet_window.window.quit()
        pet_window.window.destroy()
except Exception as e:
    print(f"程序运行异常: {e}")
    import traceback
    traceback.print_exc()
    input("按Enter键退出...")