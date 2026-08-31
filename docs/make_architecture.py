"""Render docs/architecture.png.

The diagram exists to make one argument: **StockPulse sits above the systems a
state already runs, it does not replace them.** Every state has DVDMS or
e-Aushadhi under HMIS and ABDM, and those are not going anywhere. What they
lack is data from the last mile, because the person who should enter it is
running a clinic alone.

So the layout is deliberately vertical and the existing systems are drawn at
the bottom as the foundation, with an arrow going *back down* into them from
the export. A judge should be able to see in five seconds that this is a
capture and intelligence layer, not a parallel stack.

Regenerate with:  python -m docs.make_architecture
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "architecture.png"

W, H = 1680, 1180
SCALE = 2  # supersample, then downscale, so text is not jagged

BG = (255, 255, 255)
INK = (15, 23, 42)
MUTED = (100, 116, 139)
NAVY = (30, 58, 138)
NAVY_SOFT = (219, 234, 254)
GREEN = (22, 163, 74)
GREEN_SOFT = (220, 252, 231)
AMBER = (180, 83, 9)
AMBER_SOFT = (254, 243, 199)
GREY_SOFT = (241, 245, 249)
BORDER = (203, 213, 225)


def font(size: int, bold: bool = False):
    names = (["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]
             if bold else
             ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"])
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def box(d, xy, fill, outline, radius=14, width=2):
    d.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline,
                        width=width)


def text(d, xy, s, f, fill=INK, anchor="la"):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def arrow(d, x1, y1, x2, y2, colour=NAVY, width=3, head=11, dashed=False):
    if dashed:
        total = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        steps = max(int(total // 16), 1)
        for i in range(steps):
            if i % 2:
                continue
            a = i / steps
            b = min((i + 1) / steps, 1)
            d.line([x1 + (x2 - x1) * a, y1 + (y2 - y1) * a,
                    x1 + (x2 - x1) * b, y1 + (y2 - y1) * b],
                   fill=colour, width=width)
    else:
        d.line([x1, y1, x2, y2], fill=colour, width=width)
    if y2 > y1:
        d.polygon([(x2, y2), (x2 - head, y2 - head), (x2 + head, y2 - head)],
                  fill=colour)
    else:
        d.polygon([(x2, y2), (x2 - head, y2 + head), (x2 + head, y2 + head)],
                  fill=colour)


def render() -> None:
    img = Image.new("RGB", (W * SCALE, H * SCALE), BG)
    d = ImageDraw.Draw(img)

    f_title = font(38 * SCALE, True)
    f_sub = font(21 * SCALE)
    f_band = font(15 * SCALE, True)
    f_head = font(23 * SCALE, True)
    f_body = font(17 * SCALE)
    f_small = font(15 * SCALE)
    f_tiny = font(13 * SCALE)

    def S(v):
        return v * SCALE

    text(d, (S(60), S(46)), "StockPulse — a capture and intelligence layer",
         f_title)
    text(d, (S(60), S(100)),
         "Above the systems a state already runs. Not a replacement for them.",
         f_sub, MUTED)

    # ---- Layer 1: capture -------------------------------------------------
    y0 = 168
    box(d, [S(50), S(y0), S(W - 50), S(y0 + 210)], GREY_SOFT, BORDER, 18, 2)
    text(d, (S(72), S(y0 + 18)), "1 · LAST MILE — where the data does not exist today",
         f_band, MUTED)

    modes = [
        ("Barcode", "most accurate", "needs labelled stock\nand a camera", GREEN, GREEN_SOFT),
        ("Voice", "works when nothing else does", "30 seconds, any language,\noffline-capable", NAVY, NAVY_SOFT),
        ("Chat", "when audio is impractical", "shared room, night shift,\nnoisy clinic", AMBER, AMBER_SOFT),
    ]
    mw, gap = 430, 40
    mx = 90
    for name, rank, why, colour, soft in modes:
        box(d, [S(mx), S(y0 + 52), S(mx + mw), S(y0 + 178)], soft, colour, 14, 2)
        text(d, (S(mx + 22), S(y0 + 68)), name, f_head, colour)
        text(d, (S(mx + 22), S(y0 + 102)), rank, f_small, INK)
        text(d, (S(mx + 22), S(y0 + 126)), why, f_tiny, MUTED)
        mx += mw + gap

    text(d, (S(W // 2), S(y0 + 190)),
         "PWA · offline queue in IndexedDB · syncs when connectivity returns",
         f_tiny, MUTED, anchor="ma")

    for x in (305, 735, 1165):
        arrow(d, S(x), S(y0 + 214), S(x), S(y0 + 262))

    # ---- Layer 2: one pipeline -------------------------------------------
    y1 = 432
    box(d, [S(50), S(y1), S(W - 50), S(y1 + 168)], NAVY_SOFT, NAVY, 18, 3)
    text(d, (S(72), S(y1 + 16)),
         "2 · ONE EXTRACTION PIPELINE — all three modes, identical path", f_band, NAVY)

    steps = [
        ("Gemini", "audio or text →\nstructured JSON"),
        ("Match", "against all 385 NLEM\nmedicines, threshold 85"),
        ("Confidence gate", "below 0.6 → review queue,\nnever the ledger"),
        ("Write", "append-only stock_events\n+ batch expiry"),
    ]
    sw, sgap = 350, 30
    sx = 88
    for i, (name, body) in enumerate(steps):
        box(d, [S(sx), S(y1 + 52), S(sx + sw), S(y1 + 148)], BG, NAVY, 12, 2)
        text(d, (S(sx + 18), S(y1 + 66)), name, f_body, NAVY)
        text(d, (S(sx + 18), S(y1 + 94)), body, f_tiny, INK)
        if i < len(steps) - 1:
            d.line([S(sx + sw + 4), S(y1 + 100), S(sx + sw + sgap - 4), S(y1 + 100)],
                   fill=NAVY, width=S(2))
            d.polygon([(S(sx + sw + sgap - 4), S(y1 + 100)),
                       (S(sx + sw + sgap - 14), S(y1 + 94)),
                       (S(sx + sw + sgap - 14), S(y1 + 106))], fill=NAVY)
        sx += sw + sgap

    arrow(d, S(W // 2), S(y1 + 172), S(W // 2), S(y1 + 218))

    # ---- Layer 3: intelligence -------------------------------------------
    y2 = 650
    box(d, [S(50), S(y2), S(W - 50), S(y2 + 244)], GREY_SOFT, BORDER, 18, 2)
    text(d, (S(72), S(y2 + 16)),
         "3 · INTELLIGENCE — BigQuery, asia-south1", f_band, MUTED)

    cards = [
        ("Real data at national scale",
         "200,438 facilities · 37 states\n668 districts · full NLEM 2022\nHMIS 2019-20, 21 drivers, 137 districts"),
        ("Forecasting",
         "BigQuery ML ARIMA_PLUS\n2,794 series, trained on this data\nseasonality joined from real HMIS"),
        ("Supply-chain logic",
         "lead-time reorder points · VEN ranking\nFEFO with batch expiry\nATC substitution · reporting score"),
    ]
    cw, cgap = 480, 40
    cx = 95
    for name, body in cards:
        box(d, [S(cx), S(y2 + 52), S(cx + cw), S(y2 + 212)], BG, BORDER, 14, 2)
        text(d, (S(cx + 20), S(y2 + 70)), name, f_body, NAVY)
        text(d, (S(cx + 20), S(y2 + 104)), body, f_tiny, INK)
        cx += cw + cgap

    text(d, (S(W // 2), S(y2 + 222)),
         "Districts publish 12-month seasonal multipliers per ATC class to each "
         "other. No facility or patient data ever moves.",
         f_tiny, MUTED, anchor="ma")

    # ---- Layer 4: existing systems ---------------------------------------
    y3 = 950
    box(d, [S(50), S(y3), S(W - 50), S(y3 + 178)], GREEN_SOFT, GREEN, 18, 3)
    text(d, (S(72), S(y3 + 16)),
         "4 · WHAT THE STATE ALREADY RUNS — StockPulse feeds these, it does not replace them",
         f_band, GREEN)

    existing = [
        ("DVDMS", "Drugs & Vaccine\nDistribution Management"),
        ("e-Aushadhi", "State drug\ninventory system"),
        ("HMIS", "Health Management\nInformation System"),
        ("ABDM", "Ayushman Bharat\nDigital Mission"),
    ]
    ew, egap = 350, 30
    ex = 88
    for name, body in existing:
        box(d, [S(ex), S(y3 + 52), S(ex + ew), S(y3 + 158)], BG, GREEN, 12, 2)
        text(d, (S(ex + 18), S(y3 + 68)), name, f_body, GREEN)
        text(d, (S(ex + 18), S(y3 + 98)), body, f_tiny, INK)
        ex += ew + egap

    # The export arrow: intelligence back down into the existing systems.
    arrow(d, S(W // 2), S(y2 + 250), S(W // 2), S(y3 - 6), colour=GREEN,
          width=4, head=13)
    text(d, (S(W // 2 + 26), S(y2 + 262)),
         "GET /api/v1/export/stock-events  ·  documented interchange format",
         f_small, GREEN)

    img = img.resize((W, H), Image.LANCZOS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB, {W}x{H})")


if __name__ == "__main__":
    render()
