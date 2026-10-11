import math
from pathlib import Path

from PIL import Image, ImageDraw

output_dir = Path("sample_data")
output_dir.mkdir(parents=True, exist_ok=True)


def generate_signature_1():
    # Size 320x100 RGBA transparent
    img = Image.new("RGBA", (340, 110), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    ink_color = (20, 35, 90, 240)  # Deep blue fountain pen ink

    # Draw cursive-like path for "J. Harrison"
    points = [
        (30, 75),
        (35, 30),
        (50, 20),
        (60, 35),
        (55, 75),
        (45, 90),
        (35, 80),
        (70, 70),  # J
        (75, 70),  # dot
        (85, 70),
        (95, 25),
        (100, 70),
        (100, 45),
        (115, 40),
        (120, 70),  # H
        (128, 60),
        (138, 55),
        (142, 70),  # a
        (148, 68),
        (155, 52),
        (160, 56),  # r
        (166, 68),
        (173, 52),
        (178, 56),  # r
        (185, 70),
        (190, 52),
        (195, 70),  # i
        (200, 68),
        (208, 54),
        (204, 62),
        (212, 70),  # s
        (218, 68),
        (225, 54),
        (222, 62),
        (228, 70),  # s
        (235, 62),
        (245, 52),
        (250, 68),
        (240, 70),
        (235, 62),  # o
        (255, 70),
        (260, 54),
        (268, 52),
        (274, 70),  # n
    ]

    # Smooth line
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if dist > 35:
            continue
        draw.line([p1, p2], fill=ink_color, width=3)

    # Stylish flourish underline underneath
    flourish = [(50, 85), (100, 88), (180, 82), (280, 80), (310, 75)]
    for i in range(len(flourish) - 1):
        draw.line([flourish[i], flourish[i + 1]], fill=ink_color, width=2)

    img.save(output_dir / "sample_signature_1.png", "PNG")


def generate_signature_2():
    # Size 340x110 RGBA transparent
    img = Image.new("RGBA", (340, 110), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    ink_color = (15, 23, 42, 245)  # Dark charcoal slate ink

    # Draw cursive path for "Elena Vance, Ph.D."
    points = [
        (35, 70),
        (45, 22),
        (65, 25),
        (45, 50),
        (70, 50),
        (45, 75),
        (80, 75),  # E
        (85, 75),
        (92, 30),
        (98, 75),  # l
        (104, 65),
        (114, 55),
        (118, 72),
        (106, 72),  # e
        (125, 72),
        (130, 55),
        (138, 55),
        (144, 72),  # n
        (150, 65),
        (160, 55),
        (166, 72),  # a
        # V
        (185, 45),
        (198, 80),
        (215, 35),
        (225, 42),
        (232, 65),
        (240, 55),
        (245, 72),  # a
        (252, 72),
        (258, 55),
        (265, 55),
        (270, 72),  # n
        (278, 68),
        (288, 54),
        (284, 72),  # c
        (292, 65),
        (300, 55),
        (305, 72),
        (294, 72),  # e
    ]

    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if dist > 35:
            continue
        draw.line([p1, p2], fill=ink_color, width=3)

    # Underline stroke
    draw.line([(60, 85), (320, 82)], fill=ink_color, width=2)

    img.save(output_dir / "sample_signature_2.png", "PNG")


generate_signature_1()
generate_signature_2()
print("Signatures generated successfully in sample_data/")
