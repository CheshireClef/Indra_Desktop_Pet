"""
宠物窗口类 - 支持Windows Alpha透明（修复版）
"""

import tkinter as tk
from PIL import Image, ImageTk
import os
import platform
from typing import Tuple

class PetWindow:
    def __init__(self, config):
        """初始化宠物窗口"""
        print("正在初始化宠物窗口...")
        
        self.config = config
        self.window = tk.Tk()
        self.label = None
        self.current_bg_color = 'black'  # 默认背景色
        
        # 窗口设置
        self.setup_window()
        
        # 加载宠物图片
        self.load_pet_image()
        
        # 绑定事件
        self.bind_events()
        
        # 设置窗口位置
        self.set_window_position()
        
        print("✅ 宠物窗口初始化完成")
    
    def setup_window(self):
        """设置窗口属性"""
        # 设置窗口标题
        self.window.title(self.config['pet']['name'])
        
        # 移除标题栏
        self.window.overrideredirect(True)
        
        # 设置窗口置顶
        self.window.attributes('-topmost', True)
        
        # 检查是否为Windows系统
        if platform.system() == 'Windows':
            # Windows系统：尝试使用Alpha透明
            try:
                # 尝试导入Windows透明模块
                try:
                    from ui.windows_transparency import WindowsTransparency
                except ImportError:
                    # 尝试从根目录导入
                    import sys
                    sys.path.append('.')
                    from windows_transparency import WindowsTransparency
                
                # 启用Alpha透明
                if WindowsTransparency.enable_alpha_transparency(self.window):
                    print("✅ 使用Windows API Alpha透明")
                    # 对于Alpha透明，使用纯黑色作为背景
                    self.current_bg_color = 'black'
                    self.window.config(bg=self.current_bg_color)
                else:
                    # 回退到颜色键透明
                    print("⚠️  Windows API透明失败，使用颜色键透明")
                    self.setup_color_key_transparency()
                    
            except Exception as e:
                print(f"⚠️  Windows透明初始化失败: {e}")
                import traceback
                traceback.print_exc()
                # 回退到颜色键透明
                self.setup_color_key_transparency()
        else:
            # 非Windows系统：使用颜色键透明
            self.setup_color_key_transparency()
    
    def setup_color_key_transparency(self):
        """设置颜色键透明（兼容方案）"""
        # 设置品红色为透明色
        self.current_bg_color = '#FF00FF'
        self.window.config(bg=self.current_bg_color)
        self.window.wm_attributes('-transparentcolor', self.current_bg_color)
        
        print(f"✅ 使用颜色键透明，背景色: {self.current_bg_color}")
    
    def load_pet_image(self):
        """加载宠物图片"""
        try:
            image_path = "assets/images/pet.png"
            
            if not os.path.exists(image_path):
                print(f"⚠️  图片文件不存在: {image_path}")
                # 创建默认图片
                self.create_default_image()
                return
            
            # 使用Pillow加载图片
            self.original_image = Image.open(image_path)
            
            # 检查图片模式，如果是RGBA（带Alpha通道）就保持
            if self.original_image.mode != 'RGBA':
                self.original_image = self.original_image.convert('RGBA')
            
            # 保持原始宽高比
            self.image_width, self.image_height = self.original_image.size
            
            # 创建Tkinter兼容的图片
            self.tk_image = ImageTk.PhotoImage(self.original_image)
            
            # 创建标签显示图片
            self.label = tk.Label(
                self.window,
                image=self.tk_image,
                bg=self.current_bg_color,
                bd=0
            )
            self.label.pack()
            
            # 设置窗口大小为图片大小
            self.window.geometry(f"{self.image_width}x{self.image_height}")
            
            print(f"✅ 宠物图片加载成功: {self.image_width}x{self.image_height}")
            print(f"图片模式: {self.original_image.mode}, 背景色: {self.current_bg_color}")
            
        except Exception as e:
            print(f"❌ 加载宠物图片失败: {e}")
            import traceback
            traceback.print_exc()
            self.create_default_image()
    
    def create_default_image(self):
        """创建默认图片（当找不到图片时）"""
        self.image_width = 200
        self.image_height = 300
        
        # 创建带Alpha通道的蓝色矩形
        self.default_image = Image.new(
            'RGBA', 
            (self.image_width, self.image_height), 
            (0, 0, 255, 200)  # 半透明蓝色
        )
        
        # 转换为Tkinter格式
        self.tk_image = ImageTk.PhotoImage(self.default_image)
        
        # 创建标签
        self.label = tk.Label(
            self.window,
            image=self.tk_image,
            bg=self.current_bg_color,
            bd=0
        )
        self.label.pack()
        
        # 设置窗口大小
        self.window.geometry(f"{self.image_width}x{self.image_height}")
        
        print("⚠️  使用默认蓝色矩形图片")
    
    def bind_events(self):
        """绑定事件处理"""
        if self.label:
            # 绑定左键点击事件（戳一戳）
            self.label.bind("<Button-1>", self.on_poke)
            
            # 绑定拖动事件
            self.label.bind("<ButtonPress-1>", self.start_drag)
            self.label.bind("<B1-Motion>", self.on_drag)
            self.label.bind("<ButtonRelease-1>", self.stop_drag)
            
            # 绑定右键事件到标签
            self.label.bind("<Button-3>", self.on_right_click)
            
            print("✅ 事件绑定完成")
        else:
            print("❌ 无法绑定事件：标签未创建")
    
    def on_poke(self, event):
        """处理戳一戳事件"""
        print(f"🎯 戳了宠物一下！坐标: ({event.x}, {event.y})")
        
        # 使用震动效果
        original_x = self.window.winfo_x()
        original_y = self.window.winfo_y()
        
        # 轻微震动效果
        offsets = [(3, 0), (-3, 0), (0, 3), (0, -3), (0, 0)]
        
        def apply_offset(index=0):
            if index < len(offsets):
                offset_x, offset_y = offsets[index]
                self.window.geometry(f"+{original_x + offset_x}+{original_y + offset_y}")
                self.window.after(50, lambda: apply_offset(index + 1))
        
        apply_offset()
    
    def on_right_click(self, event):
        """处理右键点击事件"""
        print(f"🖱️  右键点击: ({event.x}, {event.y})")
        
        # 右键事件将传递给上下文菜单处理
        # 这里只是确保事件被捕获
        return
    
    def start_drag(self, event):
        """开始拖动"""
        self.drag_data = {
            "x": event.x,
            "y": event.y,
            "start_x": self.window.winfo_x(),
            "start_y": self.window.winfo_y()
        }
    
    def on_drag(self, event):
        """处理拖动"""
        if hasattr(self, 'drag_data'):
            # 计算新位置
            delta_x = event.x - self.drag_data["x"]
            delta_y = event.y - self.drag_data["y"]
            
            new_x = self.drag_data["start_x"] + delta_x
            new_y = self.drag_data["start_y"] + delta_y
            
            # 防止移出屏幕
            screen_width = self.window.winfo_screenwidth()
            screen_height = self.window.winfo_screenheight()
            
            new_x = max(0, min(new_x, screen_width - self.image_width))
            new_y = max(0, min(new_y, screen_height - self.image_height))
            
            # 移动窗口
            self.window.geometry(f"+{new_x}+{new_y}")
    
    def stop_drag(self, event):
        """停止拖动"""
        if hasattr(self, 'drag_data'):
            delattr(self, 'drag_data')
            print(f"宠物位置: ({self.window.winfo_x()}, {self.window.winfo_y()})")
    
    def set_window_position(self):
        """设置窗口初始位置"""
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        
        # 计算右下角位置（留出边距）
        margin = 20
        x = screen_width - self.image_width - margin
        y = screen_height - self.image_height - margin
        
        self.window.geometry(f"+{x}+{y}")
        print(f"窗口位置设置为: ({x}, {y})")
    
    def show(self):
        """显示窗口"""
        self.window.deiconify()
    
    def hide(self):
        """隐藏窗口"""
        self.window.withdraw()
    
    def run(self):
        """运行窗口主循环"""
        self.window.mainloop()
        
    # 在 PetWindow 类中添加一个退出方法
    def quit(self):
        """安全退出窗口"""
        try:
            if self.window:
                self.window.quit()
                self.window.destroy()
        except:
            pass