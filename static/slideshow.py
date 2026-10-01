import os
import sys
import time
import random
from PIL import Image, ImageTk
import tkinter as tk

# ---------------- CONFIGURATION ----------------
IMAGE_FOLDER = "/home/pi/slideshow_images"  # Change to your folder path
DISPLAY_TIME = 5        # Seconds each image is shown
ANIMATION_STEPS = 50    # Frames per image
ZOOM_FACTOR = 1.2       # Max zoom (1.0 = no zoom)
WINDOW_WIDTH = 800      # Adjust to your screen
WINDOW_HEIGHT = 480
# ------------------------------------------------

def load_images(folder):
    """Load all supported images from a folder."""
    supported_ext = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if f.lower().endswith(supported_ext)]
    if not files:
        print("No images found in", folder)
        sys.exit(1)
    return files

def ken_burns_effect(img, step, total_steps):
    """Apply zoom and pan effect for the given step."""
    w, h = img.size
    zoom = 1.0 + (ZOOM_FACTOR - 1.0) * (step / total_steps)

    # Calculate crop size
    crop_w = int(w / zoom)
    crop_h = int(h / zoom)

    # Random pan direction (start once per image)
    if step == 0:
        ken_burns_effect.pan_x = random.randint(0, w - crop_w)
        ken_burns_effect.pan_y = random.randint(0, h - crop_h)
        ken_burns_effect.dx = random.choice([-1, 1]) * max(1, (w - crop_w) // total_steps)
        ken_burns_effect.dy = random.choice([-1, 1]) * max(1, (h - crop_h) // total_steps)

    # Update pan position
    ken_burns_effect.pan_x = max(0, min(w - crop_w, ken_burns_effect.pan_x + ken_burns_effect.dx))
    ken_burns_effect.pan_y = max(0, min(h - crop_h, ken_burns_effect.pan_y + ken_burns_effect.dy))

    # Crop and resize
    cropped = img.crop((
        ken_burns_effect.pan_x,
        ken_burns_effect.pan_y,
        ken_burns_effect.pan_x + crop_w,
        ken_burns_effect.pan_y + crop_h
    ))
    return cropped.resize((WINDOW_WIDTH, WINDOW_HEIGHT), Image.LANCZOS)

# Initialize static vars
ken_burns_effect.pan_x = 0
ken_burns_effect.pan_y = 0
ken_burns_effect.dx = 0
ken_burns_effect.dy = 0

class SlideshowApp:
    def __init__(self, root, images):
        self.root = root
        self.images = images
        self.index = 0
        self.step = 0
        self.label = tk.Label(root, bg="black")
        self.label.pack(fill="both", expand=True)
        self.show_image()

    def show_image(self):
        img_path = self.images[self.index]
        img = Image.open(img_path).convert("RGB")
        frame = ken_burns_effect(img, self.step, ANIMATION_STEPS)
        tk_img = ImageTk.PhotoImage(frame)
        self.label.config(image=tk_img)
        self.label.image = tk_img

        self.step += 1
        if self.step > ANIMATION_STEPS:
            self.step = 0
            self.index = (self.index + 1) % len(self.images)

        self.root.after(int(DISPLAY_TIME * 1000 / ANIMATION_STEPS), self.show_image)

if __name__ == "__main__":
    image_files = load_images(IMAGE_FOLDER)
    root = tk.Tk()
    root.title("Raspberry Pi Slideshow")
    root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
    root.configure(bg="black")
    root.attributes("-fullscreen", True)  # Fullscreen mode
    app = SlideshowApp(root, image_files)
    root.mainloop()
