import time
from pathlib import Path
import mss
from PIL import Image
from PySide6.QtCore import Qt, QObject, Signal, QThread  # 新增依赖
from utils import resource_path

class ScreenObserver(QObject):
    # 信号：通知主线程隐藏桌宠
    hide_pet = Signal()
    # 信号：通知主线程恢复桌宠
    restore_pet = Signal()
    def __init__(self, pet_window, settings_manager):
        """
        pet_window: PetWindow 实例
        settings_manager: SettingsManager 实例
        """
        super().__init__()
        self.pet_window = pet_window
        self.sm = settings_manager

        # 调整：统一使用resource_path处理截图保存目录
        self.output_dir = Path(resource_path("screenshots"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # 信号绑定主线程槽函数
        self.hide_pet.connect(self.pet_window._hide_for_screenshot)
        self.restore_pet.connect(self.pet_window._restore_after_screenshot)

    def observe_once(self):
        """
        手动触发一次屏幕观察：
        截图 -> 保存 -> 自动清理旧截图
        """
        print("[ScreenObserver] 开始截图")

        # 保存原始状态
        old_opacity = self.pet_window.windowOpacity()
        old_mouse_transparent = self.pet_window.testAttribute(Qt.WA_TransparentForMouseEvents)
        
        try:
            # 1. 通知主线程隐藏桌宠
            self.hide_pet.emit()
            QThread.msleep(20)  # 子线程安全延迟，替代time.sleep

            # ===== 2️⃣ 截图 =====
            with mss.mss() as sct:
                monitor = sct.monitors[0]  # 0 = 所有屏幕
                raw_img = sct.grab(monitor)

                img = Image.frombytes(
                    "RGB",
                    raw_img.size,
                    raw_img.rgb
                )

            # ===== 3️⃣ 保存 =====
            ts = time.strftime("%Y%m%d_%H%M%S")
            path = self.output_dir / f"screen_{ts}.png"
            img.save(path)
            print(f"[ScreenObserver] 截图完成：{path}")

            # ===== 5️⃣ 自动清理旧截图 =====
            self._cleanup_old_screenshots()
        finally:
            # 5. 通知主线程恢复桌宠（无论是否异常）
            self.restore_pet.emit()
        return path  # 👈 给 Qwen 用

    def _cleanup_old_screenshots(self):
        """
        只保留最近 N 张截图，其余自动删除
        """
        # ⚠️ SettingsManager.get 只支持 default，不支持 fallback
        keep_n = self.sm.get(
            "vision",
            "keep_last_n_screenshots",
            default=3
        )

        try:
            keep_n = int(keep_n)
        except Exception:
            keep_n = 3

        if keep_n <= 0:
            return

        screenshots = sorted(
            self.output_dir.glob("screen_*.png"),
            key=lambda p: p.stat().st_mtime
        )

        excess = screenshots[:-keep_n]
        for p in excess:
            try:
                p.unlink()
                print(f"[ScreenObserver] 已删除旧截图：{p.name}")
            except Exception as e:
                print(f"[ScreenObserver] 删除失败 {p}: {e}")
