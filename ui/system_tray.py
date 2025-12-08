"""
系统托盘图标 - 让程序可以优雅地退出和控制
"""

import tkinter as tk
from tkinter import Menu
import os
import sys
from PIL import Image, ImageTk

class SystemTray:
    def __init__(self, pet_window):
        """
        初始化系统托盘
        pet_window: PetWindow实例
        """
        print("初始化系统托盘...")
        
        self.pet_window = pet_window
        self.is_visible = True
        
        # 创建根窗口（隐藏的，用于托盘菜单）
        self.root = tk.Tk()
        self.root.withdraw()  # 隐藏主窗口
        self.root.title("Indra桌面宠物")  # 设置标题
        
        # 设置托盘图标
        self.setup_tray_icon()
        
        # 绑定窗口关闭事件
        self.setup_close_handler()
        
        print("✅ 系统托盘初始化完成")
    
    def setup_tray_icon(self):
        """设置托盘图标和菜单"""
        try:
            # 先创建菜单
            self.create_menu()
            
            # 然后设置图标
            self.set_icon()
            
            print("✅ 托盘图标和菜单设置完成")
            
        except Exception as e:
            print(f"⚠️  设置托盘失败: {e}")
            print("将继续运行，但没有托盘功能")
    
    def create_menu(self):
        """创建右键菜单"""
        self.menu = Menu(self.root, tearoff=0)
        
        # 添加菜单项
        self.menu.add_command(
            label="显示/隐藏宠物", 
            command=self.toggle_visibility
        )
        self.menu.add_command(
            label="戳一戳宠物", 
            command=self.poke_pet
        )
        self.menu.add_command(
            label="移动到中心", 
            command=self.move_to_center
        )
        self.menu.add_separator()
        self.menu.add_command(
            label="退出程序", 
            command=self.quit_program
        )
    
    def set_icon(self):
        """设置托盘图标"""
        # 尝试多个可能的图标路径
        icon_paths = [
            'assets/images/icon.ico',
            'assets/images/icon.png',
            'icon.ico',
        ]
        
        icon_image = None
        icon_path = None
        
        # 查找可用的图标文件
        for path in icon_paths:
            if os.path.exists(path):
                try:
                    if path.endswith('.ico'):
                        # 直接使用ICO文件
                        self.root.iconbitmap(path)
                        icon_path = path
                        print(f"✅ 加载图标文件: {path}")
                        return
                    else:
                        # 对于PNG等格式，用PIL转换
                        img = Image.open(path)
                        # 调整大小到32x32
                        img.thumbnail((32, 32), Image.Resampling.LANCZOS)
                        
                        # 转换为PhotoImage
                        photo = ImageTk.PhotoImage(img)
                        
                        # 设置窗口图标（这可能会在任务栏显示）
                        self.root.iconphoto(False, photo)
                        
                        # 保存引用防止被垃圾回收
                        self.tray_icon = photo
                        
                        icon_path = path
                        print(f"✅ 加载图片作为图标: {path}")
                        return
                        
                except Exception as e:
                    print(f"⚠️  无法加载图标 {path}: {e}")
        
        # 如果没有找到图标文件，使用默认图标
        print("⚠️  未找到图标文件，使用默认图标")
        self.set_default_icon()
    
    def set_default_icon(self):
        """设置默认图标（使用PIL创建）"""
        try:
            # 创建一个简单的默认图标
            img = Image.new('RGBA', (32, 32), (100, 150, 255, 255))
            
            # 在内存中保存为ICO
            import io
            ico_data = io.BytesIO()
            img.save(ico_data, format='ICO')
            ico_data.seek(0)
            
            # 创建一个临时文件
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.ico', delete=False) as f:
                f.write(ico_data.getvalue())
                temp_ico = f.name
            
            # 使用临时ICO文件
            self.root.iconbitmap(temp_ico)
            
            # 程序退出时删除临时文件
            import atexit
            atexit.register(os.unlink, temp_ico)
            
            print("✅ 使用生成的默认图标")
            
        except Exception as e:
            print(f"⚠️  创建默认图标失败: {e}")
            # 最后的备用方案：用文字标题
            self.root.title("🐱 Indra宠物")
    
    def setup_close_handler(self):
        """设置窗口关闭时的处理"""
        def on_closing():
            print("检测到窗口关闭，正在退出...")
            self.quit_program()
        
        self.root.protocol("WM_DELETE_WINDOW", on_closing)
    
    def toggle_visibility(self):
        """显示/隐藏宠物窗口"""
        if self.is_visible:
            self.pet_window.window.withdraw()  # 隐藏
            self.is_visible = False
            print("宠物已隐藏")
        else:
            self.pet_window.window.deiconify()  # 显示
            self.is_visible = True
            print("宠物已显示")
    
    def poke_pet(self):
        """模拟戳一戳宠物"""
        print("🎯 从托盘戳了宠物一下！")
        
        # 简单的视觉反馈
        try:
            original_bg = self.pet_window.window.cget('bg')
            self.pet_window.window.config(bg='lightyellow')
            self.pet_window.window.after(100, lambda: 
                self.pet_window.window.config(bg=original_bg))
        except:
            pass
    
    def move_to_center(self):
        """移动宠物到屏幕中心"""
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
    
    def show_menu(self, event):
        """显示右键菜单"""
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()
    
    def quit_program(self):
        """退出程序"""
        print("正在关闭程序...")
        
        # 保存设置（未来功能）
        # self.save_settings()
        
        # 优雅地关闭
        try:
            # 先销毁宠物窗口
            if hasattr(self.pet_window, 'window'):
                self.pet_window.window.quit()
            
            # 然后销毁托盘窗口
            self.root.quit()
            self.root.destroy()
        except:
            pass
        
        print("程序已退出")
        sys.exit(0)
    
    def run(self):
        """运行系统托盘"""
        print("💡 提示: 在任务栏寻找宠物图标（可能在隐藏图标区）")
        print("💡 提示: 右键图标显示控制菜单")
        
        # 绑定右键事件
        self.root.bind("<Button-3>", self.show_menu)
        
        # 运行主循环
        self.root.mainloop()