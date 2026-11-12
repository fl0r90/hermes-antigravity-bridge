---
name: antigravity-imagen
description: "Generate photorealistic images, artwork and photos using Google Imagen via Antigravity engine and deliver natively to Telegram."
version: 1.0.0
author: Dorel, Antigravity Bridge
metadata:
  hermes:
    tags: [Image, Imagen, Antigravity, Art, Drawing, Telegram, Photo]
---

# Google Imagen via Antigravity Skill

When the user asks you to draw, paint, generate, or create an image/photo (e.g. "desenează", "generează o poză cu", "fă-mi o imagine cu", "creează o imagine"):
You have direct, native access to Google Imagen via Antigravity!

### How to Generate and Deliver an Image:

1. Call the `image_generate` tool with the prompt, OR execute the helper script via terminal:
```bash
python3 /opt/data/antigravity_image_gen.py "<detailed prompt in English for best quality>"
```

2. The helper script generates the image using Antigravity, saves it to `/opt/data/generated_images/...`, and prints:
```
MEDIA:/opt/data/generated_images/hermes_...jpg
```

3. Include the `MEDIA:/opt/data/generated_images/hermes_...jpg` tag in your response along with a friendly Romanian message.
Hermes gateway automatically intercepts the `MEDIA:` directive, strips it from the visible text, and delivers the image as a high-resolution photo directly to Telegram!
