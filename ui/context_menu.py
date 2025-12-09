"""
上下文菜单管理 - 修复菜单点击后不消失的问题
"""

import tkinter as tk
from tkinter import Menu
import time

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
        self.menu = None
        
        # 创建菜单
        self.create_menu()
        
        # 绑定右键事件
        self.bind_events()
        
        print("✅ 上下文菜单初始化完成")
    
    def create_menu(self):
        """创建右键菜单"""
        if not self.pet_window or not self.pet_window.window:
            print("❌ 无法创建菜单：宠物窗口不存在")
            return
            
        try:
            self.menu = Menu(
                self.pet_window.window,
                tearoff=0,  # 不显示虚线分隔
                bg='#F0F0F0',  # 浅灰色背景
                fg='#333333',  # 深灰色文字
                activebackground='#4CAF50',  # 绿色选中背景
                activeforeground='white',
                relief='solid',  # 实线边框
                borderwidth=1,
                font=('Microsoft YaHei', 10)
            )
            
            # 添加标题（不可点击）
            self.menu.add_command(
                label=f"{self.pet_window.config['pet']['name']} - 控制菜单",
                state='disabled',
                foreground='#666666'
            )
            
            self.menu.add_separator()
            
            # 戳一戳 - 使用lambda确保菜单自动关闭
            self.menu.add_command(
                label="🔨 戳一戳",
                command=lambda: self.execute_with_menu_close(self.poke_pet),
                accelerator="左键"
            )
            
            self.menu.add_separator()
            
            # 显示/隐藏菜单项
            self.visibility_var = tk.BooleanVar(value=True)
            self.menu.add_checkbutton(
                label="👁️ 显示宠物",
                command=lambda: self.execute_with_menu_close(self.toggle_visibility),
                variable=self.visibility_var,
                onvalue=True,
                offvalue=False
            )
            
            self.menu.add_command(
                label="🎯 移动到中心",
                command=lambda: self.execute_with_menu_close(self.move_to_center)
            )
            
            self.menu.add_command(
                label="🔄 重置位置",
                command=lambda: self.execute_with_menu_close(self.reset_position)
            )
            
            self.menu.add_separator()
            
            # 系统功能
            if self.system_tray:
                self.menu.add_command(
                    label="📌 系统托盘",
                    command=lambda: self.execute_with_menu_close(self.focus_tray)
                )
            
            self.menu.add_separator()
            
            # 退出 - 使用lambda确保菜单自动关闭
            self.menu.add_command(
                label="❌ 退出程序",
                command=lambda: self.execute_with_menu_close(self.quit_program),
                foreground='#D32F2F',  # 红色文字
                activeforeground='white',
                activebackground='#D32F2F'
            )
            
        except Exception as e:
            print(f"❌ 创建菜单失败: {e}")
            import traceback
            traceback.print_exc()
    
    def execute_with_menu_close(self, func):
        """执行函数前先关闭菜单"""
        # 先关闭菜单
        self.close_menu()
        # 短暂延迟后执行函数
        self.pet_window.window.after(10, func)
    
    def close_menu(self):
        """关闭右键菜单"""
        try:
            if self.menu:
                # 使用unpost方法关闭菜单
                self.menu.unpost()
        except Exception as e:
            print(f"关闭菜单失败: {e}")
    
    def bind_events(self):
        """绑定右键事件"""
        if self.pet_window and self.pet_window.label:
            # 绑定右键事件到宠物标签
            self.pet_window.label.bind("<Button-3>", self.show_menu, add='+')
            
            # 绑定到窗口其他部分
            self.pet_window.window.bind("<Button-3>", self.show_menu, add='+')
            
            # 绑定左键点击关闭菜单
            self.pet_window.window.bind("<Button-1>", self.on_left_click, add='+')
            if self.pet_window.label:
                self.pet_window.label.bind("<Button-1>", self.on_left_click, add='+')
            
            print("✅ 右键事件绑定完成")
        else:
            print("❌ 无法绑定事件：宠物标签不存在")
    
    def on_left_click(self, event):
        """左键点击时关闭菜单"""
        self.close_menu()
    
    def show_menu(self, event):
        """显示右键菜单"""
        try:
            if not self.menu:
                self.create_menu()
                if not self.menu:
                    return
            
            # 更新显示状态
            if hasattr(self, 'visibility_var'):
                self.visibility_var.set(self.is_visible)
            
            # 在鼠标位置显示菜单
            self.menu.tk_popup(event.x_root, event.y_root)
            
            print(f"📋 显示右键菜单于 ({event.x_root}, {event.y_root})")
            
        except Exception as e:
            print(f"❌ 显示菜单失败: {e}")
    
    def poke_pet(self):
        """戳一戳宠物"""
        print("🎯 从右键菜单戳了宠物一下！")
        
        # 使用震动效果
        try:
            original_x = self.pet_window.window.winfo_x()
            original_y = self.pet_window.window.winfo_y()
            
            # 震动序列
            offsets = [(5, 0), (-5, 0), (0, 5), (0, -5), (0, 0)]
            
            def apply_offset(index=0):
                if index < len(offsets):
                    offset_x, offset_y = offsets[index]
                    self.pet_window.window.geometry(
                        f"+{original_x + offset_x}+{original_y + offset_y}"
                    )
                    if index < len(offsets) - 1:
                        self.pet_window.window.after(30, lambda: apply_offset(index + 1))
            
            apply_offset()
            
            print(f"💓 戳一戳完成，宠物位置: ({original_x}, {original_y})")
            
        except Exception as e:
            print(f"戳一戳震动效果失败: {e}")
            import traceback
            traceback.print_exc()
    
    def toggle_visibility(self):
        """切换显示/隐藏"""
        try:
            if self.is_visible:
                self.pet_window.hide()
                self.is_visible = False
                print("宠物已隐藏")
            else:
                self.pet_window.show()
                self.is_visible = True
                print("宠物已显示")
            
            # 更新菜单状态
            if hasattr(self, 'visibility_var'):
                self.visibility_var.set(self.is_visible)
            
            # 同步到系统托盘
            if self.system_tray:
                self.system_tray.is_visible = self.is_visible
                
        except Exception as e:
            print(f"切换显示状态失败: {e}")
    
    def move_to_center(self):
        """移动宠物到屏幕中心"""
        try:
            screen_width = self.pet_window.window.winfo_screenwidth()
            screen_height = self.pet_window.window.winfo_screenheight()
            
            # 使用图片的实际尺寸，而不是窗口尺寸
            if hasattr(self.pet_window, 'image_width'):
                window_width = self.pet_window.image_width
                window_height = self.pet_window.image_height
            else:
                window_width = self.pet_window.window.winfo_width()
                window_height = self.pet_window.window.winfo_height()
            
            center_x = (screen_width - window_width) // 2
            center_y = (screen_height - window_height) // 2
            
            self.pet_window.window.geometry(f"+{center_x}+{center_y}")
            print(f"宠物移动到屏幕中心: ({center_x}, {center_y})")
            
        except Exception as e:
            print(f"移动宠物失败: {e}")
    
    def reset_position(self):
        """重置位置到右下角"""
        try:
            screen_width = self.pet_window.window.winfo_screenwidth()
            screen_height = self.pet_window.window.winfo_screenheight()
            
            if hasattr(self.pet_window, 'image_width'):
                window_width = self.pet_window.image_width
                window_height = self.pet_window.image_height
            else:
                window_width = self.pet_window.window.winfo_width()
                window_height = self.pet_window.window.winfo_height()
            
            margin = 20
            x = screen_width - window_width - margin
            y = screen_height - window_height - margin
            
            self.pet_window.window.geometry(f"+{x}+{y}")
            print(f"宠物位置重置到右下角: ({x}, {y})")
            
        except Exception as e:
            print(f"重置位置失败: {e}")
    
    def focus_tray(self):
        """提示用户查看系统托盘"""
        print("💡 提示：请查看任务栏右侧的系统托盘图标")
        
        # 闪烁窗口边框提示
        try:
            original_bg = self.pet_window.current_bg_color
            
            def flash(count=0):
                if count < 4:  # 闪烁4次
                    # 临时改变窗口颜色
                    color = '#4CAF50' if count % 2 == 0 else original_bg
                    self.pet_window.window.config(bg=color)
                    self.pet_window.label.config(bg=color)
                    self.pet_window.window.after(200, lambda: flash(count + 1))
                else:
                    # 恢复原状
                    self.pet_window.window.config(bg=original_bg)
                    self.pet_window.label.config(bg=original_bg)
            
            flash()
            
        except Exception as e:
            print(f"闪烁提示失败: {e}")
    
    def quit_program(self):
        """退出程序"""
        print("正在退出程序...")
        
        # 通过系统托盘退出（如果存在）
        if self.system_tray:
            try:
                self.system_tray.quit_program(None, None)
                return  # 如果系统托盘处理了退出，就直接返回
            except:
                pass
        
        # 直接退出
        try:
            self.pet_window.window.quit()
            self.pet_window.window.destroy()
        except:
            pass
        
        import sys
        sys.exit(0)