"""
Application Icon Generator: One Mark, Every Size Windows Asks For.
==================================================================

The tray used to load IDI_APPLICATION, which is the generic Windows box that
means "this program did not bring an icon". It is the single most visible
signal that something is a script rather than a product.

The mark:

    An indigo tile carrying two paper bars and, below a gap, a shorter orange
    bar. It is a post with its fold marked. The fold is this product's whole
    idea, the point at which LinkedIn truncates an opening line on mobile, and
    the thing every hook in the studio is scored against.

Why it is drawn this simply:

    A 16 pixel icon has room for about three shapes. Anything finer turns to
    mush in the tray and the taskbar, which is where this icon actually lives.
    So the mark is three bars with generous weight, and the concept survives
    the downscale rather than being legible only at 256.

    The ground is indigo rather than the interface's near black, because a dark
    icon disappears against a dark taskbar. Indigo holds on both Windows
    themes.

Everything is rendered at 8x and downsampled with LANCZOS, because the naive
approach of drawing directly at 16 pixels produces ragged edges on the rounded
corners.

Usage:
    python tools/generate_icons.py

Outputs:
    assets/inox_hydra.ico             tray, window, shortcut, installer
    studio/frontend/icons/*.png       web app manifest sizes
    desktop/src-tauri/icons/*         the exact set the Tauri bundler expects

Strict Invariants:
- Zero em-dashes.
- Deterministic. Running this twice produces identical bytes.
"""

import os

from PIL import Image, ImageDraw, IcnsImagePlugin

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Straight from studio/frontend/styles.css, so the icon and the interface stay
# the same product rather than drifting apart.
INDIGO = (79, 70, 229, 255)      # --accent-indigo, the brand primary
PAPER = (231, 226, 213, 255)     # --accent-paper
ORANGE = (255, 106, 61, 255)     # --signal-orange, the fold warning

SUPERSAMPLE = 8
BASE = 256

# Sizes Windows actually asks for. 256 is used by the large icon views in
# Explorer, 16 by the tray and the title bar.
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]

# The manifest needs 192 and 512. Maskable needs its content inside a safe
# circle, so it is generated separately with heavier padding.
PNG_SIZES = [192, 512]


def _rounded_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def draw_mark(size, maskable=False):
    """
    Renders the mark at `size`, supersampled and downscaled.

    `maskable` insets the content so Android and Windows can crop the icon to
    any shape without clipping the bars. The spec reserves the outer 10 percent
    on each edge, so the content sits inside the middle 80 percent.
    """
    canvas = size * SUPERSAMPLE
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if maskable:
        # Fill edge to edge. The platform crops, so the ground must reach the
        # corners or a white rim appears after the crop.
        _rounded_rect(draw, (0, 0, canvas, canvas), 0, INDIGO)
        content = canvas * 0.62
    else:
        inset = canvas * 0.055
        radius = canvas * 0.215
        _rounded_rect(draw, (inset, inset, canvas - inset, canvas - inset), radius, INDIGO)
        content = canvas * 0.60

    left = (canvas - content) / 2
    bar_h = content * 0.155
    bar_r = bar_h / 2
    gap = content * 0.105

    # Two paper bars: the body of a post. The second is shorter, which reads as
    # text rather than as a stack of identical rectangles.
    top = (canvas - (bar_h * 3 + gap * 2 + content * 0.10)) / 2
    _rounded_rect(draw, (left, top, left + content, top + bar_h), bar_r, PAPER)

    second_top = top + bar_h + gap
    _rounded_rect(draw, (left, second_top, left + content * 0.74, second_top + bar_h), bar_r, PAPER)

    # The fold. Separated by a wider gap so it reads as a boundary rather than
    # a third line of text, and orange so it reads as the limit it is.
    fold_top = second_top + bar_h + gap + content * 0.10
    _rounded_rect(draw, (left, fold_top, left + content * 0.46, fold_top + bar_h), bar_r, ORANGE)

    return image.resize((size, size), Image.LANCZOS)


def main():
    assets_dir = os.path.join(REPO_ROOT, "assets")
    icons_dir = os.path.join(REPO_ROOT, "studio", "frontend", "icons")
    os.makedirs(assets_dir, exist_ok=True)
    os.makedirs(icons_dir, exist_ok=True)

    # A single .ico carrying every size, so Windows picks the right one instead
    # of scaling one badly.
    master = draw_mark(BASE)
    ico_path = os.path.join(assets_dir, "inox_hydra.ico")
    master.save(ico_path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    print(f"wrote {os.path.relpath(ico_path, REPO_ROOT)} ({', '.join(str(s) for s in ICO_SIZES)})")

    for size in PNG_SIZES:
        path = os.path.join(icons_dir, f"icon-{size}.png")
        draw_mark(size).save(path, format="PNG", optimize=True)
        print(f"wrote {os.path.relpath(path, REPO_ROOT)}")

    maskable_path = os.path.join(icons_dir, "icon-maskable-512.png")
    draw_mark(512, maskable=True).save(maskable_path, format="PNG", optimize=True)
    print(f"wrote {os.path.relpath(maskable_path, REPO_ROOT)}")

    # The Tauri bundler looks for these exact filenames. Generated from the
    # same mark rather than copied by hand, so the desktop shell cannot end up
    # wearing a different icon than the tray and the web app.
    tauri_icons = os.path.join(REPO_ROOT, "desktop", "src-tauri", "icons")
    os.makedirs(tauri_icons, exist_ok=True)

    # Linux desktop environments and package bundlers (deb, AppImage) look
    # for icons matching standard XDG hicolor theme dimensions (32, 64, 128,
    # 256, 512). Omitting any of these causes desktop environments to stretch
    # small icons or fall back to generic system place-holders.
    for size in (32, 64, 128, 256, 512):
        draw_mark(size).save(
            os.path.join(tauri_icons, f"{size}x{size}.png"),
            format="PNG",
            optimize=True,
        )
    draw_mark(256).save(os.path.join(tauri_icons, "128x128@2x.png"), format="PNG", optimize=True)
    draw_mark(512).save(os.path.join(tauri_icons, "icon.png"), format="PNG", optimize=True)

    # Windows wants the .ico file with every standard icon layer.
    master.save(
        os.path.join(tauri_icons, "icon.ico"),
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
    )

    # macOS requires an Apple Icon Image (.icns) file containing standard and
    # retina pixel layers from 16x16 up to 512x512@2x (1024x1024). A missing
    # or incomplete .icns leads to dock pixelation or failed bundle assembly.
    icns_master = draw_mark(1024)
    icns_layers = [draw_mark(s) for s in (32, 64, 128, 256, 512)]
    icns_path = os.path.join(tauri_icons, "icon.icns")
    icns_master.save(icns_path, format="ICNS", append_images=icns_layers)

    print(
        f"wrote {os.path.relpath(tauri_icons, REPO_ROOT)}{os.sep}"
        f"(32x32, 64x64, 128x128, 128x128@2x, 256x256, 512x512, icon.png, icon.ico, icon.icns)"
    )


if __name__ == "__main__":
    main()
