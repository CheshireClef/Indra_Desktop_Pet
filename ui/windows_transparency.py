"""
Windows透明窗口 - 使用Windows API实现真Alpha透明
仅适用于Windows系统
"""

import ctypes
import ctypes.wintypes
import tkinter as tk

class WindowsTransparency:
    @staticmethod
    def enable_alpha_transparency(window):
        """启用Windows Alpha透明通道"""
        try:
            # 导入Windows API
            user32 = ctypes.windll.user32
            dwmapi = ctypes.windll.dwmapi
            
            # 获取窗口句柄
            hwnd = user32.GetParent(window.winfo_id())
            
            # 1. 设置窗口样式为分层窗口（支持Alpha）
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            WS_EX_TRANSPARENT = 0x20
            
            # 获取当前样式
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            
            # 添加分层窗口样式
            user32.SetWindowLongW(
                hwnd, 
                GWL_EXSTYLE, 
                ex_style | WS_EX_LAYERED
            )
            
            # 2. 启用桌面窗口管理器（DWM）的模糊效果（Win10/11）
            try:
                # 设置窗口属性允许透明
                DWMWA_TRANSITIONS_FORCEDISABLED = 3
                DWMWA_ALLOW_NCPAINT = 4
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                
                # 禁用窗口过渡动画
                value = ctypes.c_int(1)
                dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    DWMWA_TRANSITIONS_FORCEDISABLED,
                    ctypes.byref(value),
                    ctypes.sizeof(value)
                )
            except:
                pass
            
            print("✅ Windows Alpha透明已启用")
            return True
            
        except Exception as e:
            print(f"⚠️  Windows API透明设置失败: {e}")
            return False
    
    @staticmethod
    def set_window_alpha(window, alpha):
        """设置窗口透明度（0.0-1.0）"""
        try:
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            
            # LWA_ALPHA = 0x2
            ctypes.windll.user32.SetLayeredWindowAttributes(
                hwnd,
                0,  # 颜色键 - 设为0表示不使用颜色键
                int(alpha * 255),  # Alpha值
                0x2  # LWA_ALPHA标志
            )
            return True
        except:
            return False