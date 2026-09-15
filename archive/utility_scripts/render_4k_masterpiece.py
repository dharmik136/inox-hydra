import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# =============================================================================
# 1. LOAD 3D BASE AND UPSCALE TO TRUE 4K (3840 x 3840)
# =============================================================================
base_path = "motadata_to_deloitte_4k_executive.jpg"
base = Image.open(base_path).convert("RGBA")
TARGET_SIZE = (3840, 3840)
img_4k = base.resize(TARGET_SIZE, Image.Resampling.LANCZOS)

# Direct draw on img_4k for 100% opaque screen wipes (eliminates ALL AI ghosting)
draw_canvas = ImageDraw.Draw(img_4k)

# Screen Coordinates inside the metallic tablet bezels
l_box = [440, 1380, 1670, 2430]  # Width: 1230, Height: 1050
r_box = [2170, 1380, 3400, 2430]  # Width: 1230, Height: 1050

# Paint solid 100% opaque backgrounds inside the screen bezels
draw_canvas.rounded_rectangle(l_box, radius=24, fill=(12, 18, 30, 255), outline=(56, 189, 248, 120), width=2)
draw_canvas.rounded_rectangle(r_box, radius=24, fill=(18, 16, 22, 255), outline=(245, 158, 11, 120), width=2)

# Overlay for clean vector anti-aliased drawing & typography
overlay = Image.new("RGBA", TARGET_SIZE, (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)

# Fonts setup from Windows Fonts
FONT_DIR = r"C:\Windows\Fonts"
font_banner_tag = ImageFont.truetype(f"{FONT_DIR}\\bahnschrift.ttf", 36)
font_title_main = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 80)
font_title_sub = ImageFont.truetype(f"{FONT_DIR}\\segoeui.ttf", 38)

font_screen_title = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 42)
font_screen_tab_act = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 28)
font_screen_tab_mut = ImageFont.truetype(f"{FONT_DIR}\\segoeui.ttf", 28)
font_screen_pill = ImageFont.truetype(f"{FONT_DIR}\\bahnschrift.ttf", 22)
font_screen_kpi_val = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 72)
font_screen_kpi_lbl = ImageFont.truetype(f"{FONT_DIR}\\segoeui.ttf", 26)
font_screen_axis = ImageFont.truetype(f"{FONT_DIR}\\segoeui.ttf", 22)
font_screen_status = ImageFont.truetype(f"{FONT_DIR}\\bahnschrift.ttf", 22)

font_hex_center = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 34)
font_hex_label = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 25)
font_hex_sub = ImageFont.truetype(f"{FONT_DIR}\\segoeui.ttf", 19)
font_node_badge = ImageFont.truetype(f"{FONT_DIR}\\bahnschrift.ttf", 22)
font_node_sub = ImageFont.truetype(f"{FONT_DIR}\\segoeui.ttf", 18)

font_bridge_title = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 28)
font_bridge_sub = ImageFont.truetype(f"{FONT_DIR}\\segoeui.ttf", 22)

font_bot_bold = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 34)
font_bot_sub = ImageFont.truetype(f"{FONT_DIR}\\segoeui.ttf", 26)

# Colors
CYAN_BRIGHT = (56, 189, 248, 255)
CYAN_TEAL = (45, 212, 191, 255)
CYAN_BG = (12, 18, 30, 255)
AMBER_BRIGHT = (251, 191, 36, 255)
AMBER_BG = (18, 16, 22, 255)
WHITE = (255, 255, 255, 255)
LIGHT_SLATE = (226, 232, 240, 255)
MUTED_SLATE = (148, 163, 184, 255)
GREEN_ACTIVE = (74, 222, 128, 255)

# =========================================================================
# 2. TOP EXECUTIVE GTM & SYSTEMS ARCHITECTURE BANNER
# =========================================================================
top_banner_box = [380, 110, 3460, 480]
draw.rounded_rectangle(top_banner_box, radius=32, fill=(10, 15, 26, 245), outline=(56, 189, 248, 150), width=3)

# Top GTM Badge
gtm_badge_box = [1560, 145, 2280, 210]
draw.rounded_rectangle(gtm_badge_box, radius=16, fill=(24, 30, 46, 255), outline=(251, 191, 36, 220), width=2)
draw.text((1920, 177), "GTM & SYSTEMS ARCHITECTURE", fill=AMBER_BRIGHT, font=font_banner_tag, anchor="mm")

# Main Title
draw.text((1920, 290), "BRIDGING OBSERVABILITY WITH ENTERPRISE CORE", fill=WHITE, font=font_title_main, anchor="mm")

# Subtitle
draw.text((1920, 395), "From Infrastructure Telemetry (Motadata)   ->   Global ERP Orchestration (Deloitte Consulting)", fill=LIGHT_SLATE, font=font_title_sub, anchor="mm")

# Decorative dual gradient line
draw.line([460, 470, 1920, 470], fill=(56, 189, 248, 200), width=3)
draw.line([1920, 470, 3380, 470], fill=(251, 191, 36, 200), width=3)


# =========================================================================
# 3. LEFT SCREEN: REAL-TIME OBSERVABILITY (Clean Vector Native 4K Dashboard)
# =========================================================================
# Header
draw.text((480, 1430), "REAL-TIME OBSERVABILITY", fill=WHITE, font=font_screen_title, anchor="lm")
for h_y in [1420, 1430, 1440]:
    draw.line([1615, h_y, 1645, h_y], fill=MUTED_SLATE, width=3)

# Subtabs & live pills
draw.text((480, 1495), "METRICS", fill=CYAN_BRIGHT, font=font_screen_tab_act, anchor="lm")
draw.line([480, 1515, 600, 1515], fill=CYAN_BRIGHT, width=3)
draw.text((645, 1495), "TRACES", fill=MUTED_SLATE, font=font_screen_tab_mut, anchor="lm")
draw.text((765, 1495), "LOGS", fill=MUTED_SLATE, font=font_screen_tab_mut, anchor="lm")
draw.text((860, 1495), "ALERTS", fill=MUTED_SLATE, font=font_screen_tab_mut, anchor="lm")

# Time selector pill
draw.rounded_rectangle([1040, 1475, 1260, 1515], radius=10, fill=(20, 32, 50, 255), outline=(56, 189, 248, 140), width=1)
draw.text((1150, 1495), "TIME: LAST 24H  v", fill=LIGHT_SLATE, font=font_screen_pill, anchor="mm")

# Live badge
draw.rounded_rectangle([1300, 1475, 1400, 1515], radius=10, fill=(16, 40, 32, 255), outline=(74, 222, 128, 180), width=1)
draw.ellipse([1315, 1490, 1325, 1500], fill=GREEN_ACTIVE)
draw.text((1355, 1495), "LIVE", fill=GREEN_ACTIVE, font=font_screen_pill, anchor="mm")

# Divider
draw.line([480, 1530, 1640, 1530], fill=(40, 56, 80, 200), width=1)

# Left Chart Grid Area: x from 520 to 1280, y from 1570 to 2200
y_ticks = [(1590, "500"), (1710, "400"), (1830, "300"), (1950, "200"), (2070, "100"), (2190, "0")]
for y_pos, val in y_ticks:
    draw.text((495, y_pos), val, fill=MUTED_SLATE, font=font_screen_axis, anchor="rm")
    draw.line([520, y_pos, 1280, y_pos], fill=(24, 36, 54, 255), width=1)

# Smooth Catmull-Rom spline wave
def get_spline_points(control_points, num_steps=20):
    pts = []
    for i in range(len(control_points) - 1):
        p0 = control_points[max(i - 1, 0)]
        p1 = control_points[i]
        p2 = control_points[i + 1]
        p3 = control_points[min(i + 2, len(control_points) - 1)]
        for t_step in range(num_steps):
            t = t_step / num_steps
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            pts.append((x, y))
    pts.append(control_points[-1])
    return pts

ctrl1 = [(520, 2040), (600, 1960), (700, 1920), (800, 2020), (890, 1880), (960, 1660), (1030, 1880), (1110, 1940), (1170, 1780), (1230, 1860), (1280, 1810)]
smooth_wave1 = get_spline_points(ctrl1, 15)

# Opaque gradient simulation under wave 1
fill_poly = [(520, 2190)] + smooth_wave1 + [(1280, 2190)]
draw.polygon(fill_poly, fill=(20, 42, 68, 255))

# Wave 1 Line (Cyan)
for i in range(len(smooth_wave1) - 1):
    draw.line([smooth_wave1[i], smooth_wave1[i+1]], fill=CYAN_BRIGHT, width=4)

# Wave 2 Secondary Line (Teal)
ctrl2 = [(520, 2120), (620, 2080), (720, 2100), (820, 1980), (920, 1920), (980, 1870), (1050, 2000), (1130, 2060), (1210, 1970), (1280, 1930)]
smooth_wave2 = get_spline_points(ctrl2, 15)
for i in range(len(smooth_wave2) - 1):
    draw.line([smooth_wave2[i], smooth_wave2[i+1]], fill=CYAN_TEAL, width=3)

# Peak circle indicators
peaks = [(960, 1660), (1170, 1780)]
for px, py in peaks:
    draw.ellipse([px-12, py-12, px+12, py+12], fill=CYAN_BG, outline=CYAN_BRIGHT, width=3)
    draw.ellipse([px-5, py-5, px+5, py+5], fill=WHITE)

# Vertical grid lines at timeline points
x_ticks = [(520, "00:00"), (645, "04:00"), (770, "08:00"), (895, "12:00"), (1020, "16:00"), (1145, "20:00"), (1270, "LIVE")]
for x_pos, t_lbl in x_ticks:
    draw.line([x_pos, 1570, x_pos, 2190], fill=(28, 44, 66, 255), width=1)
    color = CYAN_BRIGHT if t_lbl == "LIVE" else MUTED_SLATE
    draw.text((x_pos, 2220), t_lbl, fill=color, font=font_screen_axis, anchor="mm")

# Right KPI Cards Area: x from 1315 to 1640
# Card 1: System Health
c1_box = [1315, 1570, 1640, 1860]
draw.rounded_rectangle(c1_box, radius=16, fill=(18, 28, 44, 255), outline=(56, 189, 248, 140), width=1)
draw.text((1335, 1605), "SYSTEM HEALTH", fill=MUTED_SLATE, font=font_screen_kpi_lbl, anchor="lm")
draw.text((1335, 1680), "99.98%", fill=WHITE, font=font_screen_kpi_val, anchor="lm")
draw.rounded_rectangle([1335, 1750, 1560, 1795], radius=10, fill=(16, 40, 32, 255), outline=(74, 222, 128, 180), width=1)
draw.text((1447, 1772), "* STATUS: OPTIMAL", fill=GREEN_ACTIVE, font=font_screen_pill, anchor="mm")

# Card 2: Latency
c2_box = [1315, 1900, 1640, 2190]
draw.rounded_rectangle(c2_box, radius=16, fill=(18, 28, 44, 255), outline=(56, 189, 248, 140), width=1)
draw.text((1335, 1935), "AVG LATENCY", fill=MUTED_SLATE, font=font_screen_kpi_lbl, anchor="lm")
draw.text((1335, 2010), "14ms", fill=CYAN_BRIGHT, font=font_screen_kpi_val, anchor="lm")
draw.text((1335, 2075), "P99 Latency: 28ms", fill=LIGHT_SLATE, font=font_screen_axis, anchor="lm")
draw.text((1335, 2110), "Zero Jitter Detected", fill=MUTED_SLATE, font=font_screen_axis, anchor="lm")

# Left Bottom Status Row (y: 2280 to 2390)
draw.line([480, 2270, 1640, 2270], fill=(40, 56, 80, 255), width=1)
status_row_box = [480, 2300, 1640, 2370]
draw.rounded_rectangle(status_row_box, radius=12, fill=(12, 18, 28, 255), outline=(40, 60, 90, 220), width=1)
draw.text((540, 2335), "* UPTIME: 99.99%", fill=CYAN_BRIGHT, font=font_screen_status, anchor="lm")
draw.text((810, 2335), "|  PACKET LOSS: 0.00%", fill=WHITE, font=font_screen_status, anchor="lm")
draw.text((1150, 2335), "|  MOTADATA TELEMETRY: 12+ MODULES ACTIVE", fill=LIGHT_SLATE, font=font_screen_status, anchor="lm")


# =========================================================================
# 4. RIGHT SCREEN: ENTERPRISE RESOURCE PLANNING (Clean Vector Diagram)
# =========================================================================
HEX_CENTER_X = 2785
HEX_CENTER_Y = 1885

def get_hex_points(cx, cy, r):
    pts = []
    for i in range(6):
        angle_deg = 60 * i - 30
        rad = math.radians(angle_deg)
        pts.append((cx + r * math.cos(rad), cy + r * math.sin(rad)))
    return pts

R_ORBIT = 285
R_HEX = 112

hex_modules = [
    (270, "FINANCE", "SAP FICO"),              # Top (12 o'clock)
    (330, "HR & TALENT", "SuccessFactors"),    # Top-Right (2 o'clock)
    (30,  "CRM & SALES", "SAP CX"),            # Bot-Right (4 o'clock)
    (90,  "DATA PLATFORM", "BTP & HANA"),      # Bottom (6 o'clock)
    (150, "OPERATIONS", "S/4HANA Core"),       # Bot-Left (8 o'clock)
    (210, "SUPPLY CHAIN", "SAP SCM"),          # Top-Left (10 o'clock)
]

# STEP 1: Draw lines FIRST so polygons cover them cleanly!
# 1a. Connecting lines from Center Hex to Perimeter Hexagons
for angle, title, sub in hex_modules:
    rad = math.radians(angle)
    hx = HEX_CENTER_X + R_ORBIT * math.cos(rad)
    hy = HEX_CENTER_Y + R_ORBIT * math.sin(rad)
    draw.line([HEX_CENTER_X, HEX_CENTER_Y, hx, hy], fill=(245, 158, 11, 180), width=3)

# 1b. Inter-connecting ring between surrounding hexagons
for i in range(len(hex_modules)):
    a1, _, _ = hex_modules[i]
    a2, _, _ = hex_modules[(i + 1) % len(hex_modules)]
    r1, r2 = math.radians(a1), math.radians(a2)
    p1 = (HEX_CENTER_X + R_ORBIT * math.cos(r1), HEX_CENTER_Y + R_ORBIT * math.sin(r1))
    p2 = (HEX_CENTER_X + R_ORBIT * math.cos(r2), HEX_CENTER_Y + R_ORBIT * math.sin(r2))
    draw.line([p1, p2], fill=(245, 158, 11, 120), width=2)

# 1c. Peripheral Branch Lines
peripheral_nodes = [
    {"start_angle": 210, "end": (2290, 1535), "title": "API GATEWAY", "sub": "Enterprise Conduits"},
    {"start_angle": 270, "end": (2785, 1425), "title": "GLOBAL INTEGRATION", "sub": "Multi-Region Core"},
    {"start_angle": 330, "end": (3280, 1535), "title": "GTM STRATEGY", "sub": "Value Realization"},
    {"start_angle": 30,  "end": (3280, 2235), "title": "DEMAND FORECAST", "sub": "Predictive SCM"},
    {"start_angle": 90,  "end": (2785, 2335), "title": "COMPLIANCE & AUDIT", "sub": "Enterprise Governance"},
    {"start_angle": 150, "end": (2290, 2235), "title": "HYBRID CLOUD", "sub": "Resilient Scale"},
]

for pnode in peripheral_nodes:
    rad = math.radians(pnode["start_angle"])
    hx = HEX_CENTER_X + R_ORBIT * math.cos(rad)
    hy = HEX_CENTER_Y + R_ORBIT * math.sin(rad)
    ex, ey = pnode["end"]
    mid_x = (hx + ex) / 2
    draw.line([hx, hy, mid_x, ey], fill=(251, 191, 36, 180), width=2)
    draw.line([mid_x, ey, ex, ey], fill=(251, 191, 36, 180), width=2)

# STEP 2: Center Hexagon (Core S/4HANA & ERP) drawn over center lines
CENTER_HEX_R = 142
pts_c_outer = get_hex_points(HEX_CENTER_X, HEX_CENTER_Y, CENTER_HEX_R)
draw.polygon(pts_c_outer, fill=(32, 24, 18, 255), outline=AMBER_BRIGHT)
pts_c_mid = get_hex_points(HEX_CENTER_X, HEX_CENTER_Y, CENTER_HEX_R - 9)
draw.polygon(pts_c_mid, fill=(24, 18, 14, 255), outline=(251, 191, 36, 220))

draw.text((HEX_CENTER_X, HEX_CENTER_Y - 34), "ENTERPRISE", fill=WHITE, font=font_hex_center, anchor="mm")
draw.text((HEX_CENTER_X, HEX_CENTER_Y), "RESOURCE", fill=WHITE, font=font_hex_center, anchor="mm")
draw.text((HEX_CENTER_X, HEX_CENTER_Y + 34), "PLANNING", fill=AMBER_BRIGHT, font=font_hex_center, anchor="mm")

# STEP 3: Surrounding Hexagons drawn over all lines!
for angle, title, sub in hex_modules:
    rad = math.radians(angle)
    hx = HEX_CENTER_X + R_ORBIT * math.cos(rad)
    hy = HEX_CENTER_Y + R_ORBIT * math.sin(rad)
    pts_outer = get_hex_points(hx, hy, R_HEX)
    draw.polygon(pts_outer, fill=(28, 22, 32, 255), outline=(251, 191, 36, 240))
    pts_inner = get_hex_points(hx, hy, R_HEX - 7)
    draw.polygon(pts_inner, fill=(20, 18, 26, 255), outline=(245, 158, 11, 160))
    draw.text((hx, hy - 11), title, fill=WHITE, font=font_hex_label, anchor="mm")
    draw.text((hx, hy + 16), sub, fill=AMBER_BRIGHT, font=font_hex_sub, anchor="mm")

# STEP 4: Peripheral Badges drawn over branch lines!
for pnode in peripheral_nodes:
    ex, ey = pnode["end"]
    bw, bh = 220, 52
    bbox = [ex - bw//2, ey - bh//2, ex + bw//2, ey + bh//2]
    draw.rounded_rectangle(bbox, radius=12, fill=(16, 22, 32, 255), outline=AMBER_BRIGHT, width=2)
    draw.text((ex, ey - 8), pnode["title"], fill=WHITE, font=font_node_badge, anchor="mm")
    draw.text((ex, ey + 13), pnode["sub"], fill=AMBER_BRIGHT, font=font_node_sub, anchor="mm")

# Right Bottom Status Row
draw.line([2200, 2370, 3370, 2370], fill=(80, 60, 40, 255), width=1)
draw.text((2785, 2398), "GLOBAL ERP ORCHESTRATION   *   DELOITTE CONSULTATIVE OFFERING", fill=LIGHT_SLATE, font=font_screen_status, anchor="mm")


# =========================================================================
# 5. CENTER CONDUIT CALLOUT (Positioned in 470px gap with ZERO overlap)
# =========================================================================
bridge_box = [1740, 1975, 2100, 2065]
draw.rounded_rectangle(bridge_box, radius=18, fill=(12, 18, 30, 255), outline=(255, 255, 255, 220), width=2)
draw.text((1920, 2005), "EVENT-DRIVEN BRIDGE", fill=WHITE, font=font_bridge_title, anchor="mm")
draw.text((1920, 2038), "Live Telemetry  ->  Enterprise Action", fill=AMBER_BRIGHT, font=font_bridge_sub, anchor="mm")


# =========================================================================
# 6. BOTTOM PLATFORM EXECUTIVE BANNER
# =========================================================================
bot_exec_box = [640, 3380, 3200, 3500]
draw.rounded_rectangle(bot_exec_box, radius=24, fill=(10, 16, 28, 245), outline=(100, 116, 139, 180), width=2)
draw.text((1920, 3422), "MOTADATA IT OBSERVABILITY   |   DELOITTE CONSULTATIVE OFFERING (SAP)", fill=WHITE, font=font_bot_bold, anchor="mm")
draw.text((1920, 3462), "Connecting Infrastructure Reliability to Mission-Critical Enterprise Architecture", fill=MUTED_SLATE, font=font_bot_sub, anchor="mm")

# Footer stamp
draw.text((1920, 3760), "4K ULTRA-HIGH DEFINITION  *  EXECUTIVE SYSTEMS ARCHITECTURE SPECIFICATION", fill=(100, 115, 135, 220), font=font_screen_status, anchor="mm")


# =========================================================================
# 7. COMPOSITE AND SAVE MASTERPIECE
# =========================================================================
final = Image.alpha_composite(img_4k, overlay)
final_rgb = final.convert("RGB")

output_file = "motadata_to_deloitte_4k_perfect.jpg"
final_rgb.save(output_file, quality=98, optimize=True)
print(f"Masterpiece successfully rendered and saved to {output_file} at {final_rgb.size}!")
