import time
from pathlib import Path

import mss
from PIL import Image
from PySide6.QtCore import Qt


class ScreenObserver:
    def __init__(self, pet_window, settings_manager):
        """
        pet_window: PetWindow 实例
        settings_manager: SettingsManager 实例
        """
        self.pet_window = pet_window
        self.sm = settings_manager

        # 截图保存目录
        self.output_dir = Path("screenshots")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def observe_once(self):
        """
        手动触发一次屏幕观察：
        截图 -> 保存 -> 自动清理旧截图
        """
        print("[ScreenObserver] 开始截图")

        # ===== 1️⃣ 临时隐藏桌宠（接受闪烁，压到最短）=====
        old_opacity = self.pet_window.windowOpacity()

        self.pet_window.setWindowOpacity(0.0)
        self.pet_window.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.pet_window.repaint()

        # 尽量短，低于这个容易截到桌宠
        time.sleep(0.02)

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

        # ===== 4️⃣ 恢复桌宠 =====
        self.pet_window.setWindowOpacity(old_opacity)
        self.pet_window.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        # ===== 5️⃣ 自动清理旧截图 =====
        self._cleanup_old_screenshots()

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
