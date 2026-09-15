from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

# Load base 1024x1024 image
base_path = "motadata_to_deloitte_4k_executive.jpg"
base = Image.open(base_path).convert("RGBA")

# Upscale to full 4K resolution (3840 x 3840) using high-quality Lanczos resampling
TARGET_SIZE = (3840, 3840)
img_4k = base.resize(TARGET_SIZE, Image.Resampling.LANCZOS)

# Create drawing overlays
overlay = Image.new("RGBA", TARGET_SIZE, (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)

# Font configurations
FONT_DIR = r"C:\Windows\Fonts"
font_title_large = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 76)
font_title_med = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 52)
font_title_small = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 38)
font_sub_bold = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 32)
font_body = ImageFont.truetype(f"{FONT_DIR}\\segoeui.ttf", 28)
font_caption = ImageFont.truetype(f"{FONT_DIR}\\segoeui.ttf", 22)
font_badge = ImageFont.truetype(f"{FONT_DIR}\\bahnschrift.ttf", 30)

# Colors
CYAN_GLOW = (56, 189, 248, 255)       # #38bdf8
AMBER_GLOW = (251, 191, 36, 255)      # #fbbf24
WHITE = (255, 255, 255, 255)
LIGHT_GRAY = (226, 232, 240, 230)
MUTED_GRAY = (148, 163, 184, 210)
DARK_BG = (15, 23, 42, 220)           # Slate 900 semi-transparent

# =========================================================================
# 1. TOP GTM & ENTERPRISE ARCHITECTURE BANNER (As requested by Dharmik)
# =========================================================================
banner_box = [420, 140, 3420, 480]
# Draw rounded dark glass card
draw.rounded_rectangle(banner_box, radius=36, fill=(10, 15, 28, 225), outline=(71, 85, 105, 180), width=3)

# Subtle ambient gradient line under top banner
draw.line([460, 470, 3380, 470], fill=(56, 189, 248, 120), width=3)

# Top badge
badge_box = [1640, 175, 2200, 235]
draw.rounded_rectangle(badge_box, radius=18, fill=(30, 41, 59, 240), outline=(56, 189, 248, 200), width=2)
draw.text((1920, 205), "GTM & SYSTEMS ARCHITECTURE", fill=CYAN_GLOW, font=font_badge, anchor="mm")

# Main Title
draw.text((1920, 305), "BRIDGING OBSERVABILITY WITH ENTERPRISE CORE", fill=WHITE, font=font_title_large, anchor="mm")

# Subtitle
draw.text((1920, 395), "From Infrastructure Telemetry (Motadata) ➔ Global ERP Orchestration (Deloitte Consulting)", fill=LIGHT_GRAY, font=font_title_small, anchor="mm")

# =========================================================================
# 2. CLEAN UP & POLISH RIGHT PANEL (ENTERPRISE ERP)
# =========================================================================
# Scale factor from 1024 to 3840 is 3.75
scale = 3.75

def to_4k(x, y):
    return (int(x * scale), int(y * scale))

# Right panel peripheral callout boxes to cover AI smudges and place crystal clear labels
right_callouts = [
    # (x, y, text, align)
    (545, 242, "GLOBAL INTEGRATION", "LEFT"),
    (905, 200, "GTM STRATEGY", "RIGHT"),
    (740, 335, "DEMAND FORECASTING", "RIGHT"),
    (880, 875, "DATA GOVERNANCE", "RIGHT"),
    (385, 840, "API WORKFLOWS", "LEFT"),
]

# Specifically replace the blurry labels on the right panel
# Box 1: Top Left peripheral (near 545, 242 in 1024 space -> 2043, 907)
# Let's cleanly patch and draw crisp text for all 6 callouts surrounding the hexagon cluster:

labels_right = [
    # Top-Left: replaces 'GLOAAL NITEGHARON' / 'GATN'
    {"box": [2030, 860, 2420, 940], "text": "GLOBAL INTEGRATION", "color": AMBER_GLOW},
    # Top-Right: replaces 'STR8CS'
    {"box": [3130, 715, 3480, 795], "text": "GTM STRATEGY", "color": AMBER_GLOW},
    # Mid-Right: replaces 'FORECASTING'
    {"box": [3000, 1990, 3450, 2070], "text": "DEMAND FORECASTING", "color": AMBER_GLOW},
    # Bottom-Right: replaces 'SORI6ES'
    {"box": [3130, 3210, 3480, 3290], "text": "DATA GOVERNANCE", "color": AMBER_GLOW},
    # Bottom-Left: replaces 'GATA'
    {"box": [2050, 3100, 2380, 3180], "text": "API GATEWAY", "color": AMBER_GLOW},
]

for item in labels_right:
    # Patch over blurry background with sleek dark glass capsule
    draw.rounded_rectangle(item["box"], radius=18, fill=(12, 17, 30, 240), outline=(217, 119, 6, 180), width=2)
    # Centered sharp text
    cx = (item["box"][0] + item["box"][2]) // 2
    cy = (item["box"][1] + item["box"][3]) // 2
    draw.text((cx, cy), item["text"], fill=WHITE, font=font_sub_bold, anchor="mm")

# =========================================================================
# 3. POLISH LEFT PANEL (REAL-TIME OBSERVABILITY)
# =========================================================================
# Bottom timeline clean replacement (at y ~ 2650-2750 in 4K)
# Draw clean metrics timeline bar
draw.rounded_rectangle([700, 2820, 1750, 2920], radius=20, fill=(12, 20, 36, 235), outline=(56, 189, 248, 160), width=2)
timeline_points = ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "LIVE NOW"]
for i, pt in enumerate(timeline_points):
    px = 750 + i * 160
    color = CYAN_GLOW if i == 6 else MUTED_GRAY
    draw.text((px, 2870), pt, fill=color, font=font_caption, anchor="mm")

# Clean up bottom stats bar on left panel
draw.rounded_rectangle([420, 3240, 1780, 3340], radius=22, fill=(10, 16, 30, 240), outline=(56, 189, 248, 180), width=2)
draw.text((620, 3290), "UPTIME: 99.98%", fill=CYAN_GLOW, font=font_badge, anchor="mm")
draw.text((1100, 3290), "•  NETWORK LATENCY: 14ms  •", fill=WHITE, font=font_badge, anchor="mm")
draw.text((1580, 3290), "ALERTS: 0 CRITICAL", fill=(74, 222, 128, 255), font=font_badge, anchor="mm")

# Clean up bottom stats bar on right panel
draw.rounded_rectangle([2060, 3420, 3480, 3520], radius=22, fill=(16, 20, 32, 240), outline=(251, 191, 36, 180), width=2)
draw.text((2320, 3470), "ERP: SAP S/4HANA", fill=AMBER_GLOW, font=font_badge, anchor="mm")
draw.text((2770, 3470), "•  PROCESS GOVERNANCE  •", fill=WHITE, font=font_badge, anchor="mm")
draw.text((3240, 3470), "STATUS: OPTIMAL", fill=(74, 222, 128, 255), font=font_badge, anchor="mm")

# =========================================================================
# 4. CENTER OPTICAL CONDUIT BADGE
# =========================================================================
draw.rounded_rectangle([1650, 1860, 2190, 1980], radius=24, fill=(15, 23, 42, 245), outline=(255, 255, 255, 180), width=2)
draw.text((1920, 1905), "EVENT-DRIVEN BRIDGE", fill=WHITE, font=font_sub_bold, anchor="mm")
draw.text((1920, 1945), "Real-time Telemetry ➔ Business Execution", fill=MUTED_GRAY, font=font_caption, anchor="mm")

# =========================================================================
# 5. BOTTOM METADATA FOOTER
# =========================================================================
footer_y = 3720
draw.text((1920, footer_y), "DELOITTE CONSULTATIVE OFFERING  •  ENTERPRISE SYSTEMS & OBSERVABILITY  •  4K ULTRA-HD", fill=(100, 116, 139, 220), font=font_caption, anchor="mm")

# Merge overlays
final_4k = Image.alpha_composite(img_4k, overlay)
final_rgb = final_4k.convert("RGB")

output_filename = "motadata_to_deloitte_4k_crystal_clear.jpg"
final_rgb.save(output_filename, quality=96, optimize=True)
print(f"Saved {output_filename} successfully at {final_rgb.size} resolution!")
