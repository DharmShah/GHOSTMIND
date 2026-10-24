import os
from PIL import Image

def generate_icons(output_dir="."):
    ico_path = os.path.join(output_dir, "app_icon.ico")
    png_path = os.path.join(output_dir, "app_icon.png")

    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]

    if os.path.exists(png_path):
        # Convert user's latest app_icon.png to multi-resolution Windows ICO
        base_img = Image.open(png_path).convert("RGBA")
        resized_imgs = [base_img.resize(s, Image.Resampling.LANCZOS) for s in sizes]
        resized_imgs[0].save(
            ico_path,
            format="ICO",
            sizes=sizes,
            append_images=resized_imgs[1:]
        )
        print(f"Generated {ico_path} from latest {png_path} successfully!")
    else:
        print(f"Warning: {png_path} not found.")

if __name__ == "__main__":
    generate_icons()
