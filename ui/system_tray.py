"""
系统托盘图标 - 让程序可以优雅地退出和控制
"""

import tkinter as tk
from tkinter import Menu
import threading
import sys
import os

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
        
        # 设置托盘图标
        self.setup_tray_icon()
        
        # 绑定窗口关闭事件
        self.setup_close_handler()
        
        print("✅ 系统托盘初始化完成")
    
    def setup_tray_icon(self):
        """设置托盘图标和菜单"""
        try:
            # 创建菜单
            self.menu = Menu(self.root, tearoff=0)
            
            # 添加菜单项
            self.menu.add_command(
                label="显示/隐藏宠物", 
                command=self.toggle_visibility
            )
            self.menu.add_separator()
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
            
            # 绑定右键事件到窗口（显示菜单）
            self.root.bind("<Button-3>", self.show_menu)
            
            print("✅ 托盘菜单创建完成")
            
        except Exception as e:
            print(f"⚠️  创建托盘菜单失败: {e}")
    
    def setup_close_handler(self):
        """设置窗口关闭时的处理"""
        def on_closing():
            print("正在退出程序...")
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
        # 可以在这里触发宠物的戳一戳反应
        
        # 简单的视觉反馈：让窗口闪烁一下
        original_bg = self.pet_window.window.cget('bg')
        self.pet_window.window.config(bg='lightyellow')
        self.pet_window.window.after(100, lambda: 
            self.pet_window.window.config(bg=original_bg))
    
    def move_to_center(self):
        """移动宠物到屏幕中心"""
        screen_width = self.pet_window.window.winfo_screenwidth()
        screen_height = self.pet_window.window.winfo_screenheight()
        
        window_width = self.pet_window.window.winfo_width()
        window_height = self.pet_window.window.winfo_height()
        
        center_x = (screen_width - window_width) // 2
        center_y = (screen_height - window_height) // 2
        
        self.pet_window.window.geometry(f"+{center_x}+{center_y}")
        print(f"宠物移动到屏幕中心: ({center_x}, {center_y})")
    
    def show_menu(self, event):
        """显示右键菜单"""
        try:
            self.menu.post(event.x_root, event.y_root)  # 改用post
        finally:
            self.menu.grab_release()
    
    def quit_program(self):
        """退出程序"""
        print("正在关闭程序...")
        
        # 保存最后的位置（未来功能）
        # self.save_last_position()
        
        # 销毁所有窗口
        try:
            self.root.quit()
            self.root.destroy()
            self.pet_window.window.quit()
            self.pet_window.window.destroy()
        except:
            pass
        
        print("程序已退出")
        os._exit(0)  # 强制退出
    
    def run(self):
        """运行系统托盘"""
        print("系统托盘已启动，右键任务栏图标可显示菜单")
        
        # 在主线程中运行tkinter主循环
        self.root.mainloop()