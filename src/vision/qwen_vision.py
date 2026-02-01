# src/vision/qwen_vision.py
"""
Qwen 视觉模型客户端
负责调用 Qwen-VL (或兼容的 Vision API) 对图片内容进行描述。
"""
import base64
import requests
from pathlib import Path
from utils import resource_path

class QwenVisionClient:
    """
    Qwen 视觉客户端类
    封装了 API 请求构建、图片 Base64 编码和响应解析。
    """
    def __init__(self, api_url: str, api_key: str, model: str):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model

    def describe_image(self, image_path: Path) -> str:
        """
        将截图发送给 Qwen 视觉模型，返回文字概括
        """
        # 调整：统一处理图片路径
        abs_image_path = Path(resource_path(str(image_path)))
        image_b64 = self._encode_image(abs_image_path)

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请客观、简要地描述这张屏幕截图的内容，描述用户此时可能在做什么，如果看到视频和游戏窗口，将一部分重点放在视频和游戏窗口的描述上。回答字数控制在200字以内不要分段。"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}"
                            }
                        }
                    ]
                }
            ],
            "stream": False,
            "max_tokens": 512,
            "temperature": 0.2
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        resp = requests.post(self.api_url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()

        data = resp.json()
        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _encode_image(path: Path) -> str:
        """读取图片文件并转换为 Base64 编码字符串"""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
