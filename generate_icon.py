"""
generate_icon.py — Generates icon.ico for MTG Budget Builder.

Pixel-art design: wad of green banknotes with brown tape wrapping around them.
Run once with: .venv/Scripts/python generate_icon.py
"""

from PIL import Image, ImageDraw


def make_base(work: int = 32) -> Image.Image:
    """
    Draw the icon at `work` x `work` pixels.
    All coordinates are specified in a 32x32 virtual grid.
    """
    img = Image.new("RGBA", (work, work), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    s = work / 32  # scale factor for all coordinates

    def R(x1, y1, x2, y2, fill, outline=None):
        d.rectangle(
            [round(x1 * s), round(y1 * s), round(x2 * s), round(y2 * s)],
            fill=fill, outline=outline,
        )

    def L(x1, y1, x2, y2, fill, w=1):
        d.line(
            [round(x1 * s), round(y1 * s), round(x2 * s), round(y2 * s)],
            fill=fill, width=max(1, round(w * s)),
        )

    # ── Palette ─────────────────────────────────────────────────────────────
    BLACK    = (16,  16,  16, 255)   # outline
    G3       = (26,  82,  32, 255)   # back bill
    G2       = (44, 122,  50, 255)   # middle bill
    G1       = (66, 165,  72, 255)   # front bill
    G_SHINE  = (112, 198, 118, 255)  # front-bill edge highlight
    G_LINE   = (182, 220, 185, 255)  # faint detail lines on front bill
    T_DARK   = ( 60,  38,  24, 255)  # tape shadow edge
    T_BODY   = (104,  68,  46, 255)  # tape main
    T_LIGHT  = (150, 108,  82, 255)  # tape highlight stripe

    # ── Bill stack (drawn back → front) ──────────────────────────────────────
    # Bill 3 — furthest back, offset right+down
    R( 7,  9, 27, 25, G3, BLACK)
    # Bill 2 — middle
    R( 5,  7, 25, 23, G2, BLACK)
    # Bill 1 — front (main)
    R( 2,  5, 23, 21, G1, BLACK)

    # Front-bill corner highlights (top edge + left edge)
    L( 3,  6, 22,  6, G_SHINE)
    L( 3,  6,  3, 20, G_SHINE)

    # Front-bill horizontal detail lines (suggest printed design / text rows)
    L( 5, 10, 20, 10, G_LINE)
    L( 5, 16, 20, 16, G_LINE)

    # ── Brown tape band (spans full width, overlaps all bills) ────────────────
    R( 0, 12, 31, 16, T_BODY)             # body
    L( 0, 12, 31, 12, T_DARK)             # top shadow edge
    L( 0, 16, 31, 16, T_DARK)             # bottom shadow edge
    L( 0, 13, 31, 13, T_LIGHT)            # highlight stripe

    return img


def generate(path: str = "icon.ico"):
    sizes = [256, 48, 32, 16]
    images = [make_base(s) for s in sizes]

    images[0].save(
        path,
        format="ICO",
        append_images=images[1:],
    )
    print(f"Saved {path}  ({', '.join(str(s) + 'px' for s in sizes)})")

    preview = make_base(32).resize((128, 128), Image.NEAREST)
    preview.save("icon_preview.png")
    print("Saved icon_preview.png  (128px preview, nearest-neighbour)")


def generate_icns(path: str = "icon.icns"):
    """Generate a macOS .icns file from the pixel-art icon.
    Must be run on macOS — requires the 'iconutil' command-line tool.
    """
    import os, subprocess, tempfile, shutil

    # macOS iconset sizes (filename format required by iconutil)
    iconset_sizes = [
        (16,   "icon_16x16.png"),
        (32,   "icon_16x16@2x.png"),
        (32,   "icon_32x32.png"),
        (64,   "icon_32x32@2x.png"),
        (128,  "icon_128x128.png"),
        (256,  "icon_128x128@2x.png"),
        (256,  "icon_256x256.png"),
        (512,  "icon_256x256@2x.png"),
        (512,  "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]

    iconset_dir = path.replace(".icns", ".iconset")
    os.makedirs(iconset_dir, exist_ok=True)

    for size, filename in iconset_sizes:
        img = make_base(size)
        img.save(os.path.join(iconset_dir, filename))
        print(f"  {filename}")

    subprocess.run(["iconutil", "-c", "icns", iconset_dir, "-o", path], check=True)
    shutil.rmtree(iconset_dir)
    print(f"Saved {path}")


if __name__ == "__main__":
    import sys
    if "--icns" in sys.argv:
        generate_icns()
    else:
        generate()
