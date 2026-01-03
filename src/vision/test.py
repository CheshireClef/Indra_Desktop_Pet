from pathlib import Path
from qwen_vision import QwenVisionClient

# ⚠️ 这里直接手填，测试完可以删
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
API_KEY = "sk-fipprepqdmmfohtzmruwriakmfpzvwucsddzmfculgqhhlbn"
MODEL = "Qwen/Qwen3-VL-32B-Instruct"

client = QwenVisionClient(
    api_url=API_URL,
    api_key=API_KEY,
    model=MODEL
)

# 换成你真实存在的一张截图路径
image_path = Path("screenshots/screen_20260103_212028.png")

result = client.describe_image(image_path)
print("====== Qwen 返回结果 ======")
print(result)
