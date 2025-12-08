# create_icon.py
from PIL import Image, ImageDraw

# 创建一个简单的图标
img = Image.new('RGBA', (32, 32), (255, 200, 200, 255))
draw = ImageDraw.Draw(img)

# 画一个简单的猫脸
draw.ellipse([6, 6, 26, 26], fill=(100, 150, 255))  # 蓝色脸
draw.ellipse([10, 12, 14, 16], fill=(255, 255, 255))  # 左眼
draw.ellipse([18, 12, 22, 16], fill=(255, 255, 255))  # 右眼
draw.arc([10, 18, 22, 24], 0, 180, fill=(255, 100, 100), width=2)  # 微笑

# 保存为ICO
img.save('assets/images/icon.ico', format='ICO')
print("图标已创建: assets/images/icon.ico")