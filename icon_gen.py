from PIL import Image, ImageDraw

def draw_cartoon_cloud(draw, size):
    """
    画一个经典卡通云朵（符号级）
    """
    w, h = size, size
    cloud_color = (170, 170, 170, 255)

    # 基于 size 的比例
    r = int(w * 0.18)
    y = int(h * 0.45)

    # 三个主圆
    draw.ellipse(
        [w * 0.25 - r, y - r, w * 0.25 + r, y + r],
        fill=cloud_color
    )
    draw.ellipse(
        [w * 0.45 - r * 1.2, y - r * 1.4, w * 0.45 + r * 1.2, y + r * 1.4],
        fill=cloud_color
    )
    draw.ellipse(
        [w * 0.65 - r, y - r, w * 0.65 + r, y + r],
        fill=cloud_color
    )

    # 云底
    draw.rectangle(
        [w * 0.18, y, w * 0.78, y + r * 1.4],
        fill=cloud_color
    )

def draw_classic_lightning(draw, size):
    """
    画一个经典倾斜锯齿闪电
    """
    w, h = size, size
    lightning_color = (25, 45, 130, 255)

    points = [
        (w * 0.52, h * 0.38),
        (w * 0.62, h * 0.38),
        (w * 0.48, h * 0.65),
        (w * 0.58, h * 0.65),
        (w * 0.42, h * 0.90),
        (w * 0.48, h * 0.60),
        (w * 0.40, h * 0.60),
    ]

    draw.polygon(points, fill=lightning_color)

def create_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw_cartoon_cloud(draw, size)
    draw_classic_lightning(draw, size)

    return img

def main():
    sizes = [16, 32, 48, 64]
    icons = [create_icon(s) for s in sizes]

    icons[0].save(
        "storm_tray_icon.ico",
        format="ICO",
        sizes=[(s, s) for s in sizes]
    )

    print("已生成 storm_tray_icon.ico（经典卡通云 + 锯齿闪电）")

if __name__ == "__main__":
    main()
