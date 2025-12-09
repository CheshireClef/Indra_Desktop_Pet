"""
上下文菜单管理 - 处理宠物右键菜单
"""

import tkinter as tk
from tkinter import Menu
import threading

class ContextMenu:
    def __init__(self, pet_window, system_tray=None):
        """
        初始化上下文菜单
        pet_window: PetWindow实例
        system_tray: 系统托盘实例（可选，用于同步状态）
        """
        print("初始化上下文菜单...")
        
        self.pet_window = pet_window
        self.system_tray = system_tray
        self.is_visible = True
        
        # 创建菜单
        self.create_menu()
        
        # 绑定右键事件
        self.bind_events()
        
        print("✅ 上下文菜单初始化完成")
    
    def create_menu(self):
        """创建右键菜单"""
        self.menu = Menu(
            self.pet_window.window,
            tearoff=0,  # 不显示虚线分隔
            bg='white',
            fg='black',
            activebackground='#4CAF50',
            activeforeground='white',
            font=('Microsoft YaHei', 10)
        )
        
        # 添加菜单项
        self.menu.add_command(
            label="戳一戳",
            command=self.poke_pet,
            compound='left'
        )
        
        self.menu.add_separator()
        
        # 显示/隐藏菜单项
        self.visibility_var = tk.BooleanVar(value=True)
        self.menu.add_checkbutton(
            label="显示宠物",
            command=self.toggle_visibility,
            variable=self.visibility_var,
            onvalue=True,
            offvalue=False
        )
        
        self.menu.add_command(
            label="移动到屏幕中心",
            command=self.move_to_center
        )
        
        self.menu.add_separator()
        
        # 系统功能
        self.menu.add_command(
            label="打开系统托盘",
            command=self.focus_tray
        )
        
        self.menu.add_command(
            label="退出程序",
            command=self.quit_program
        )
        
        # 添加版本信息（只读）
        self.menu.add_separator()
        self.menu.add_command(
            label="Indra Desktop Pet v0.3",
            state='disabled'  # 禁用状态，只能显示
        )
    
    def bind_events(self):
        """绑定右键事件到宠物标签"""
        # 绑定到宠物标签
        self.pet_window.label.bind("<Button-3>", self.show_menu)  # 右键
        
        # 也可以绑定到窗口其他部分
        self.pet_window.window.bind("<Button-3>", self.show_menu)
    
    def show_menu(self, event):
        """显示右键菜单"""
        try:
            # 更新显示状态
            if hasattr(self, 'visibility_var'):
                self.visibility_var.set(self.is_visible)
            
            # 在鼠标位置显示菜单
            self.menu.tk_popup(event.x_root, event.y_root)
            
            # 确保菜单获得焦点
            self.menu.focus_set()
            
        finally:
            # 确保菜单释放
            self.menu.grab_release()
    
    def poke_pet(self):
        """戳一戳宠物"""
        print("🎯 从右键菜单戳了宠物一下！")
        
        # 视觉反馈
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
        
        # 如果连接到系统托盘，也触发它的戳一戳
        if self.system_tray:
            try:
                # 使用线程避免阻塞
                threading.Thread(target=self.system_tray.poke_pet, args=(None, None), daemon=True).start()
            except:
                pass
    
    def toggle_visibility(self):
        """切换显示/隐藏"""
        if self.is_visible:
            self.pet_window.window.withdraw()
            self.is_visible = False
            print("宠物已隐藏")
        else:
            self.pet_window.window.deiconify()
            self.is_visible = True
            print("宠物已显示")
        
        # 同步到系统托盘
        if self.system_tray:
            self.system_tray.is_visible = self.is_visible
    
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
    
    def focus_tray(self):
        """聚焦到系统托盘（提示用户）"""
        print("💡 提示：请查看任务栏的系统托盘图标")
        
        # 可以添加闪烁效果提示
        try:
            original_bg = self.pet_window.window.cget('bg')
            
            def flash(count=0):
                if count < 3:  # 闪烁3次
                    color = 'lightblue' if count % 2 == 0 else original_bg
                    self.pet_window.window.config(bg=color)
                    self.pet_window.window.after(200, lambda: flash(count + 1))
                else:
                    self.pet_window.window.config(bg=original_bg)
            
            flash()
        except:
            pass
    
    def quit_program(self):
        """退出程序"""
        print("正在退出程序...")
        
        # 通过系统托盘退出（如果存在）
        if self.system_tray:
            self.system_tray.quit_program(None, None)
        else:
            # 直接退出
            self.pet_window.window.quit()
            self.pet_window.window.destroy()
            import sys
            sys.exit(0)