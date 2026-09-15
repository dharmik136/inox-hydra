from PIL import Image, ImageDraw, ImageFont

# Load the base 1024x1024 executive graphic
base_path = "motadata_to_deloitte_4k_executive.jpg"
base = Image.open(base_path).convert("RGBA")

# Upscale to full 4K (3840 x 3840)
TARGET_SIZE = (3840, 3840)
img_4k = base.resize(TARGET_SIZE, Image.Resampling.LANCZOS)

# Create high-res drawing overlay
overlay = Image.new("RGBA", TARGET_SIZE, (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)

# Fonts
FONT_DIR = r"C:\Windows\Fonts"
font_header_tag = ImageFont.truetype(f"{FONT_DIR}\\bahnschrift.ttf", 34)
font_title_main = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 78)
font_title_sub = ImageFont.truetype(f"{FONT_DIR}\\segoeui.ttf", 38)
font_label_bold = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 32)
font_label_med = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 26)
font_label_small = ImageFont.truetype(f"{FONT_DIR}\\segoeui.ttf", 24)
font_badge = ImageFont.truetype(f"{FONT_DIR}\\bahnschrift.ttf", 26)

# Color Palette
CYAN_ACCENT = (56, 189, 248, 255)      # #38bdf8
AMBER_ACCENT = (251, 191, 36, 255)     # #fbbf24
WHITE = (255, 255, 255, 255)
LIGHT_SLATE = (226, 232, 240, 240)
MUTED_SLATE = (148, 163, 184, 220)
GREEN_ACTIVE = (74, 222, 128, 255)

# =========================================================================
# 1. TOP GTM & ENTERPRISE ARCHITECTURE BANNER
# =========================================================================
top_banner_box = [380, 110, 3460, 480]
draw.rounded_rectangle(top_banner_box, radius=32, fill=(10, 15, 26, 235), outline=(56, 189, 248, 140), width=3)

# Top GTM Badge
gtm_badge_box = [1560, 145, 2280, 210]
draw.rounded_rectangle(gtm_badge_box, radius=16, fill=(20, 30, 48, 245), outline=(251, 191, 36, 200), width=2)
draw.text((1920, 177), "GTM & SYSTEMS ARCHITECTURE", fill=AMBER_ACCENT, font=font_header_tag, anchor="mm")

# Main Title
draw.text((1920, 290), "BRIDGING OBSERVABILITY WITH ENTERPRISE CORE", fill=WHITE, font=font_title_main, anchor="mm")

# Subtitle (clean ASCII characters, no glyph missing)
draw.text((1920, 395), "From Infrastructure Telemetry (Motadata)   ->   Global ERP Orchestration (Deloitte Consulting)", fill=LIGHT_SLATE, font=font_title_sub, anchor="mm")

draw.line([460, 470, 3380, 470], fill=(56, 189, 248, 100), width=2)


# =========================================================================
# 2. RIGHT PANEL: ENTERPRISE RESOURCE PLANNING (Perfect Margins & Padding)
# =========================================================================
right_labels = [
    # Top-Left 1 (replaces 'GATN' at 2220, 1545)
    {"center": (2220, 1545), "w": 200, "h": 52, "text": "API GATEWAY"},
    # Top-Left 2 (replaces 'GLOAAL NITEGHARON' at 2430, 1555 - cleanly away from FINANCE)
    {"center": (2430, 1555), "w": 200, "h": 52, "text": "INTEGRATION"},
    # Top-Right 1 (replaces 'ANALYTICS' at 2950, 1545)
    {"center": (2950, 1545), "w": 200, "h": 52, "text": "CORE ANALYTICS"},
    # Top-Right 2 (replaces 'STR8CS' at 3260, 1495)
    {"center": (3260, 1495), "w": 220, "h": 52, "text": "GTM STRATEGY"},
    # Mid-Left (replaces 'GLOAAL INTEGRATION' at 2210, 1925 - comfortably left of the conduit)
    {"center": (2210, 1925), "w": 200, "h": 52, "text": "HYBRID CLOUD"},
    # Mid-Right (replaces 'FORECASTING' at 3250, 1925)
    {"center": (3250, 1925), "w": 250, "h": 52, "text": "DEMAND FORECAST"},
    # Bottom-Left 1 (replaces 'GATA' at 2220, 2305)
    {"center": (2220, 2305), "w": 200, "h": 52, "text": "DATA PIPELINES"},
    # Bottom-Left 2 (replaces 'ANALYTICS' at 2430, 2295 - cleanly away from DATA FLOWS)
    {"center": (2430, 2295), "w": 200, "h": 52, "text": "AUTOMATION"},
    # Bottom-Right 1 (replaces 'FORECASTING' at 2960, 2305)
    {"center": (2960, 2305), "w": 210, "h": 52, "text": "COMPLIANCE"},
    # Bottom-Right 2 (replaces 'SORI6ES' at 3260, 2340)
    {"center": (3260, 2340), "w": 210, "h": 52, "text": "AI WORKFLOWS"},
]

for item in right_labels:
    cx, cy = item["center"]
    hw, hh = item["w"] // 2, item["h"] // 2
    box = [cx - hw, cy - hh, cx + hw, cy + hh]
    draw.rounded_rectangle(box, radius=12, fill=(16, 20, 32, 250), outline=(217, 119, 6, 200), width=2)
    draw.text((cx, cy), item["text"], fill=WHITE, font=font_badge, anchor="mm")


# =========================================================================
# 3. LEFT PANEL: REAL-TIME OBSERVABILITY (Clean Vector Polish)
# =========================================================================
# 1. Dropdown pill button at (1175, 1660)
dd_box = [1040, 1630, 1310, 1690]
draw.rounded_rectangle(dd_box, radius=14, fill=(24, 34, 52, 250), outline=(56, 189, 248, 160), width=2)
draw.text((1175, 1660), "TIME: LAST 24H  v", fill=LIGHT_SLATE, font=font_label_small, anchor="mm")

# 2. Bottom axis clean numbers at y=2232
axis_box = [500, 2205, 1370, 2260]
draw.rectangle(axis_box, fill=(14, 20, 32, 255))
timeline_labels = ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "LIVE"]
for i, tl in enumerate(timeline_labels):
    tx = 530 + i * 135
    color = CYAN_ACCENT if i == 6 else MUTED_SLATE
    draw.text((tx, 2232), tl, fill=color, font=font_label_small, anchor="mm")

# 3. Bottom status bar at y=2370-2425
bot_status_box = [460, 2365, 1580, 2425]
draw.rectangle(bot_status_box, fill=(14, 20, 32, 255))
draw.text((540, 2395), "UPTIME: 99.99%", fill=CYAN_ACCENT, font=font_label_small, anchor="mm")
draw.text((820, 2395), "*  AVG LATENCY: 12ms", fill=WHITE, font=font_label_small, anchor="mm")
draw.text((1160, 2395), "*  PACKET LOSS: 0.00%", fill=WHITE, font=font_label_small, anchor="mm")
draw.text((1490, 2395), "HEALTH: OPTIMAL", fill=GREEN_ACTIVE, font=font_label_small, anchor="mm")


# =========================================================================
# 4. CENTER CONDUIT CALLOUT
# =========================================================================
conduit_box = [1640, 1860, 2190, 1980]
draw.rounded_rectangle(conduit_box, radius=20, fill=(12, 18, 32, 250), outline=(255, 255, 255, 200), width=2)
draw.text((1915, 1905), "EVENT-DRIVEN BRIDGE", fill=WHITE, font=font_label_bold, anchor="mm")
draw.text((1915, 1945), "Live Telemetry  ->  Business Execution", fill=AMBER_ACCENT, font=font_label_small, anchor="mm")


# =========================================================================
# 5. BOTTOM PLATFORM EXECUTIVE BANNER
# =========================================================================
bot_exec_box = [680, 3380, 3160, 3500]
draw.rounded_rectangle(bot_exec_box, radius=24, fill=(10, 16, 28, 235), outline=(100, 116, 139, 160), width=2)
draw.text((1920, 3422), "MOTADATA IT OBSERVABILITY   |   DELOITTE CONSULTATIVE OFFERING (SAP)", fill=WHITE, font=font_label_bold, anchor="mm")
draw.text((1920, 3462), "Connecting Infrastructure Reliability to Mission-Critical Enterprise Architecture", fill=MUTED_SLATE, font=font_label_small, anchor="mm")

# Footer stamp
draw.text((1920, 3760), "4K ULTRA-HIGH DEFINITION  *  EXECUTIVE SYSTEMS ARCHITECTURE SPECIFICATION", fill=(90, 105, 125, 200), font=font_label_small, anchor="mm")

# Composite and save
final = Image.alpha_composite(img_4k, overlay)
final_rgb = final.convert("RGB")

output_file = "motadata_to_deloitte_4k_perfect.jpg"
final_rgb.save(output_file, quality=97, optimize=True)
print(f"Masterpiece re-saved cleanly as {output_file} at {final_rgb.size} resolution!")
