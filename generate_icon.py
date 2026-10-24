import os
from PIL import Image, ImageDraw

def generate_icons(output_dir="."):
    ico_path = os.path.join(output_dir, "app_icon.ico")
    png_path = os.path.join(output_dir, "app_icon.png")

    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    images = []

    for size in sizes:
        w, h = size
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Rounded rectangle background with pastel lavender gradient effect
        margin = int(w * 0.06)
        radius = int(w * 0.25)
        draw.rounded_rectangle(
            [margin, margin, w - margin, h - margin],
            radius=radius,
            fill=(203, 185, 245, 255),
            outline=(180, 160, 230, 255),
            width=max(1, int(w * 0.02))
        )

        # Central 4-point star/sparkle motif
        cx, cy = w // 2, h // 2
        r_outer = int(w * 0.28)
        r_inner = int(w * 0.10)

        points = [
            (cx, cy - r_outer),
            (cx + r_inner, cy - r_inner),
            (cx + r_outer, cy),
            (cx + r_inner, cy + r_inner),
            (cx, cy + r_outer),
            (cx - r_inner, cy + r_inner),
            (cx - r_outer, cy),
            (cx - r_inner, cy - r_inner)
        ]
        # Soft shadow + white sparkle
        shadow_pts = [(x + int(w * 0.015), y + int(h * 0.015)) for x, y in points]
        draw.polygon(shadow_pts, fill=(140, 120, 190, 160))
        draw.polygon(points, fill=(255, 255, 255, 255))
        images.append(img)

    images[0].save(png_path)
    images[0].save(
        ico_path,
        format="ICO",
        sizes=[(im.width, im.height) for im in images],
        append_images=images[1:]
    )
    print(f"Generated icon: {ico_path} and {png_path}")

if __name__ == "__main__":
    generate_icons()
