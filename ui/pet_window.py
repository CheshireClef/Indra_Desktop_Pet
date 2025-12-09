"""
宠物主窗口 - 显示在桌面上的宠物
使用真实立绘图片版本
"""

import tkinter as tk
from PIL import Image, ImageTk
import os

class PetWindow:
    def __init__(self, config=None, system_tray=None):
        """
        初始化宠物窗口
        config: 配置字典
        system_tray: 系统托盘实例（可选）
        """
        print("正在创建宠物窗口...")
        
        self.config = config or {}
        self.system_tray = system_tray
        
        # 创建主窗口
        self.window = tk.Tk()
        self.window.title("因陀罗桌宠")
        
        # 设置窗口属性
        self.setup_window()
        
        # 显示宠物
        self.show_pet()
        
        # 上下文菜单将在外部初始化
        
    def setup_window(self):
        """设置窗口属性"""
        # 1. 无边框窗口
        self.window.overrideredirect(True)
        
        # 2. 始终置顶（保持在最前面）
        self.window.wm_attributes('-topmost', True)
        
        # 3. 设置大小和位置
        width = self.config.get('pet', {}).get('width', 150)
        height = self.config.get('pet', {}).get('height', 150)
        
        pos_x = self.config.get('window', {}).get('pos_x', 500)
        pos_y = self.config.get('window', {}).get('pos_y', 300)
        
        self.window.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        
        # 4. 设置白色背景，并让白色透明
        self.window.config(bg='white')
        self.window.wm_attributes('-transparentcolor', 'white')
        
        print(f"窗口属性设置完成: {width}x{height}, 位置({pos_x}, {pos_y})")
        
    def show_pet(self):
        """显示宠物图片 - 加载真实立绘"""
        print("正在加载宠物立绘...")
        
        # 尝试从不同位置加载图片
        image_paths = [
            'assets/images/pet.png',
            'pet_stand.png',
            'pet.png',
        ]
        
        # 优先使用配置中的路径
        config_path = self.config.get('pet', {}).get('image_path')
        if config_path:
            image_paths.insert(0, config_path)
        
        pet_image = None
        used_path = None
        
        # 尝试每个可能的路径
        for path in image_paths:
            if os.path.exists(path):
                try:
                    pet_image = Image.open(path)
                    used_path = path
                    print(f"✅ 找到立绘文件: {path}")
                    break
                except Exception as e:
                    print(f"⚠️  无法打开图片 {path}: {e}")
        
        if pet_image is None:
            print("❌ 未找到立绘图片，将创建备用图片")
            # 创建备用图片
            pet_image = Image.new('RGBA', (150, 150), (200, 230, 255, 255))
            used_path = "生成的备用图片"
        
        try:
            # 调整图片大小（如果需要）
            width = self.config.get('pet', {}).get('width', 150)
            height = self.config.get('pet', {}).get('height', 150)
            
            # 保持宽高比调整大小
            pet_image.thumbnail((width, height), Image.Resampling.LANCZOS)
            
            # 转换成tkinter能显示的格式
            self.pet_img = ImageTk.PhotoImage(pet_image)
            
            # 创建标签显示图片
            self.label = tk.Label(self.window, image=self.pet_img, bg='white')
            self.label.pack()
            
            print(f"✅ 立绘加载成功: {used_path}")
            print(f"   图片尺寸: {pet_image.size}")
            
        except Exception as e:
            # 如果处理真实图片失败，用文字代替
            print(f"❌ 处理立绘失败: {e}")
            print("改用文字显示宠物")
            
            self.label = tk.Label(
                self.window, 
                text="🐱", 
                font=("Arial", 50),
                bg='white'
            )
            self.label.pack()
        
        # 绑定事件：点击和拖动
        self.setup_interaction()
        print("事件绑定完成")
    
    def setup_interaction(self):
        """设置交互事件"""
        # 绑定左键点击事件（戳一戳）
        self.label.bind("<Button-1>", self.on_click_start)
        self.label.bind("<ButtonRelease-1>", self.on_click_end)
        
        # 绑定拖动事件
        self.label.bind("<B1-Motion>", self.on_drag)
        
        # 记录拖动起始位置
        self.drag_start_x = 0
        self.drag_start_y = 0
        
        # 注意：右键事件将在ContextMenu中绑定
    
    def on_click_start(self, event):
        """鼠标按下（开始戳）"""
        print("😊 宠物被戳中！")
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        
        # 视觉反馈：轻微放大效果
        try:
            original_size = (self.window.winfo_width(), self.window.winfo_height())
            # 暂时放大5%
            new_width = int(original_size[0] * 1.05)
            new_height = int(original_size[1] * 1.05)
            self.window.geometry(f"{new_width}x{new_height}")
        except:
            pass
    
    def on_click_end(self, event):
        """鼠标释放（戳完了）"""
        print("👌 戳一戳完成")
        
        # 恢复原始大小
        try:
            width = self.config.get('pet', {}).get('width', 150)
            height = self.config.get('pet', {}).get('height', 150)
            self.window.geometry(f"{width}x{height}")
        except:
            pass
    
    def on_drag(self, event):
        """拖动宠物窗口"""
        delta_x = event.x - self.drag_start_x
        delta_y = event.y - self.drag_start_y
        
        x = self.window.winfo_x() + delta_x
        y = self.window.winfo_y() + delta_y
        
        self.window.geometry(f"+{x}+{y}")
        
        # 确保窗口不会完全移出屏幕
        self.keep_on_screen(x, y)
    
    def keep_on_screen(self, x, y):
        """确保窗口不会完全移出屏幕"""
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        
        window_width = self.window.winfo_width()
        window_height = self.window.winfo_height()
        
        if x < -window_width + 20:
            x = -window_width + 20
        if x > screen_width - 20:
            x = screen_width - 20
        if y < -window_height + 20:
            y = -window_height + 20
        if y > screen_height - 20:
            y = screen_height - 20
        
        if x != self.window.winfo_x() or y != self.window.winfo_y():
            self.window.geometry(f"+{x}+{y}")
    
    def run(self):
        """运行窗口主循环"""
        print("\n" + "=" * 50)
        print("🎮 宠物已就绪！")
        print("📌 操作指南:")
        print("  1. 左键点击: 戳一戳互动")
        print("  2. 右键点击: 显示控制菜单")
        print("  3. 按住拖动: 移动宠物位置")
        print("  4. 关闭方法: 右键菜单或系统托盘")
        print("=" * 50 + "\n")
        
        self.window.mainloop()