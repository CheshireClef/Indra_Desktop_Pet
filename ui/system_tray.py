# ui/system_tray.py
"""
高级系统托盘 - 使用pystray库，更可靠的托盘图标
"""

import threading
import time
from PIL import Image, ImageDraw
import os
import sys

class AdvancedTray:
    def __init__(self, pet_window):
        """
        初始化高级系统托盘
        pet_window: PetWindow实例
        """
        print("初始化高级系统托盘...")
        
        self.pet_window = pet_window
        self.is_visible = True
        
        # 确保有图标文件
        self.ensure_icon()
        
        # 创建托盘图标
        self.setup_tray()
        
        print("✅ 高级系统托盘初始化完成")
    
    def ensure_icon(self):
        """确保图标文件存在"""
        # 尝试多个可能的图标路径
        icon_paths = [
            'assets/images/icon.ico',
            'assets/images/icon.png',
            'images/icon.ico',
            'images/icon.png',
            'icon.ico',
            'pet_stand.png',
        ]
        
        self.icon_path = None
        
        for path in icon_paths:
            if os.path.exists(path):
                self.icon_path = path
                print(f"✅ 找到图标文件: {path}")
                break
        
        if not self.icon_path:
            print("⚠️  未找到图标文件，创建默认图标")
            self.create_default_icon('assets/images/default_icon.png')
            self.icon_path = 'assets/images/default_icon.png'
    
    def create_default_icon(self, path):
        """创建默认图标"""
        # 创建目录
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # 创建一个32x32的图标
        image = Image.new('RGBA', (32, 32), (255, 200, 200, 0))
        draw = ImageDraw.Draw(image)
        
        # 画一个简单的猫头
        draw.ellipse([4, 4, 28, 28], fill=(100, 150, 255))  # 蓝色头
        draw.ellipse([10, 12, 14, 16], fill=(255, 255, 255))  # 左眼
        draw.ellipse([18, 12, 22, 16], fill=(255, 255, 255))  # 右眼
        draw.arc([10, 18, 22, 24], 0, 180, fill=(255, 100, 100), width=2)  # 微笑
        
        image.save(path, 'PNG')
        print(f"✅ 默认图标已创建: {path}")
    
    def setup_tray(self):
        """设置托盘图标和菜单"""
        try:
            import pystray
            print("✅ pystray库加载成功")
        except ImportError:
            print("❌ 未安装pystray库，请运行: pip install pystray")
            return
        
        # 加载图标
        try:
            icon_image = Image.open(self.icon_path)
            print(f"✅ 加载图标: {self.icon_path}")
        except Exception as e:
            print(f"⚠️  无法加载图标: {e}，使用纯色图标")
            icon_image = Image.new('RGB', (32, 32), (100, 150, 255))
        
        # 创建菜单
        menu_items = []
        
        # 显示/隐藏宠物
        menu_items.append(
            pystray.MenuItem(
                "显示/隐藏宠物",
                self.toggle_visibility,
                checked=lambda item: self.is_visible
            )
        )
        
        menu_items.append(pystray.Menu.SEPARATOR)
        
        # 戳一戳宠物
        menu_items.append(
            pystray.MenuItem(
                "戳一戳宠物",
                self.poke_pet
            )
        )
        
        # 移动到中心
        menu_items.append(
            pystray.MenuItem(
                "移动到中心",
                self.move_to_center
            )
        )
        
        menu_items.append(pystray.Menu.SEPARATOR)
        
        # 退出程序
        menu_items.append(
            pystray.MenuItem(
                "退出程序",
                self.quit_program
            )
        )
        
        # 创建菜单
        menu = pystray.Menu(*menu_items)
        
        # 创建托盘图标
        self.icon = pystray.Icon(
            "indra_pet",
            icon_image,
            "Indra桌面宠物",
            menu
        )
    
    def toggle_visibility(self, icon, item):
        """显示/隐藏宠物窗口"""
        # Tkinter操作必须在主线程中执行
        if self.is_visible:
            # 使用after在主线程中执行
            self.pet_window.window.after(0, self.pet_window.window.withdraw)
            self.is_visible = False
            print("宠物已隐藏")
        else:
            self.pet_window.window.after(0, self.pet_window.window.deiconify)
            self.is_visible = True
            print("宠物已显示")
    
    def poke_pet(self, icon, item):
        """模拟戳一戳宠物"""
        print("🎯 从托盘戳了宠物一下！")
        
        # 在主线程中执行Tkinter操作
        def do_poke():
            try:
                original_bg = self.pet_window.window.cget('bg')
                self.pet_window.window.config(bg='lightyellow')
                
                def restore_bg():
                    try:
                        self.pet_window.window.config(bg=original_bg)
                    except:
                        pass
                
                self.pet_window.window.after(100, restore_bg)
            except Exception as e:
                print(f"戳一戳反馈失败: {e}")
        
        self.pet_window.window.after(0, do_poke)
    
    def move_to_center(self, icon, item):
        """移动宠物到屏幕中心"""
        def do_move():
            try:
                screen_width = self.pet_window.window.winfo_screenwidth()
                screen_height = self.pet_window.window.winfo_screenheight()
                
                window_width = self.pet_window.window.winfo_width()
                window_height = self.pet_window.window.winfo_height()
                
                center_x = (screen_width - window_width) // 2
                center_y = (screen_height - window_height) // 2
                
                self.pet_window.window.geometry(f"+{center_x}+{center_y}")
                print(f"宠物移动到屏幕中心: ({center_x}, {center_y})")
            except Exception as e:
                print(f"移动宠物失败: {e}")
        
        self.pet_window.window.after(0, do_move)
    
    def quit_program(self, icon, item):
        """退出程序"""
        print("正在退出程序...")
        
        # 停止托盘图标
        if hasattr(self, 'icon'):
            self.icon.stop()
        
        # 在主线程中退出
        def do_quit():
            try:
                self.pet_window.window.quit()
                self.pet_window.window.destroy()
            except:
                pass
            print("程序已退出")
            sys.exit(0)
        
        self.pet_window.window.after(0, do_quit)
    
    def run_in_background(self):
        """在后台运行托盘图标"""
        if not hasattr(self, 'icon'):
            print("⚠️  托盘图标未创建，跳过后台运行")
            return
        
        print("💡 启动系统托盘后台线程...")
        
        # 在新线程中运行托盘图标
        def tray_thread_func():
            try:
                self.icon.run()
            except Exception as e:
                print(f"托盘图标运行失败: {e}")
        
        tray_thread = threading.Thread(target=tray_thread_func, daemon=True)
        tray_thread.start()
        print("✅ 系统托盘在后台运行")