import time
from pathlib import Path

import mss
from PIL import Image
from PySide6.QtCore import Qt


class ScreenObserver:
    def __init__(self, pet_window):
        """
        pet_window: PetWindow 实例
        """
        self.pet_window = pet_window

        # 截图保存目录
        self.output_dir = Path("screenshots")
        self.output_dir.mkdir(exist_ok=True)

    def observe_once(self):
        """
        手动触发一次屏幕观察（Step 1：只截图）
        """
        print("[ScreenObserver] 开始截图")

        # ===== 1️⃣ 让桌宠“隐形”而不是 hide =====
        old_opacity = self.pet_window.windowOpacity()

        self.pet_window.setWindowOpacity(0.0)
        self.pet_window.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.pet_window.repaint()

        # 给系统极短的时间刷新（几乎无感）
        time.sleep(0.05)

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
