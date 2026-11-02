"""Champ Market Labs 'XAUUSD Daily Outlook' card.

Draws the day's date, 1H candles, levels and scenarios onto the fixed artwork
in card_template.webp (the brand design with the old numbers removed).
Everything is drawn at 2x and scaled down so text and candles stay sharp.
"""
import os
import datetime as dt
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "card_template.webp")
FONTS = HERE
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
S = 2  # supersampling

WHITE = (244, 244, 244, 255)
SOFT = (205, 210, 218, 255)
GREY = (150, 158, 170, 255)
GOLD = (243, 205, 110, 255)
RED = (255, 69, 69, 255)
GREEN = (46, 220, 120, 255)
YEL = (245, 200, 60, 255)
CANDLE_UP = (38, 200, 110, 255)
CANDLE_DN = (240, 70, 70, 255)

# chart panel geometry (1x coordinates of the template)
PX0, PX1 = 46, 1030      # plot left / price-axis line
PY0, PY1 = 350, 800      # plot top / bottom (keeps clear of the corner scripts)
CANDLE_X1 = 770          # candles end here, pills live on the right
PILL_R = 1020


def font(weight, size):
    return ImageFont.truetype(os.path.join(FONTS, f"Inter-{weight}.otf"), int(size * S))


def num(v):
    return f"{int(round(v))}"


def zn(z):
    return f"{z[0]} – {z[1]}"


def available():
    return os.path.exists(TEMPLATE)


def _pill(d, right, cy, text, col, fnt, dark_text=False):
    tw = d.textlength(text, font=fnt)
    h, padx = 38 * S, 14 * S
    x1 = right * S
    x0 = x1 - tw - 2 * padx
    y0, y1 = cy * S - h / 2, cy * S + h / 2
    face = tuple(int(c * 0.28) for c in col[:3]) + (235,)
    d.rounded_rectangle((x0, y0, x1, y1), radius=7 * S, fill=face, outline=col, width=int(1.6 * S))
    d.text(((x0 + x1) / 2, cy * S), text, font=fnt, fill=WHITE, anchor="mm")
    return x0 / S


def _dashed(d, x0, x1, y, col, dash=8, gap=6, width=1.6):
    x = x0
    while x < x1:
        d.line(((x * S, y * S), (min(x + dash, x1) * S, y * S)), fill=col, width=int(width * S))
        x += dash + gap


def _fit(d, text, weight, size, maxw):
    while size > 14:
        f = font(weight, size)
        if d.textlength(text, font=f) <= maxw * S:
            return f
        size -= 1
    return font(weight, size)


def bias_label(ctx):
    s4 = ctx["t4"][0]
    intra = ctx["s1"] + ctx["s15"]
    if s4 < 0 and intra >= 1:
        return "Bias: Bearish, Recovering", YEL
    if s4 > 0 and intra <= -1:
        return "Bias: Bullish, Pulling Back", YEL
    if s4 < 0:
        return "Bias: Bearish", RED
    if s4 > 0:
        return "Bias: Bullish", GREEN
    if intra >= 1:
        return "Bias: Neutral to Bullish", GREEN
    if intra <= -1:
        return "Bias: Neutral to Bearish", RED
    return "Bias: Neutral", YEL


def subtitle(ctx):
    l4 = ctx["t4"][1]
    t4 = {"bearish": "4H bearish", "bullish": "4H bullish", "recovery": "4H recovering inside a downtrend",
          "pullback": "4H pulling back inside an uptrend", "range": "4H range-bound"}[l4]
    t1 = {1: "1H bullish", -1: "1H bearish", 0: "1H neutral"}[ctx["s1"]]
    t15 = {1: "15M buying pressure", -1: "15M selling pressure", 0: "15M consolidating"}[ctx["s15"]]
    return f"{t4}; {t1}; {t15}."


def make_card(ctx, path):
    base = Image.open(TEMPLATE).convert("RGBA")
    W, H = base.size
    ov = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    # ---- date ----
    dd = ctx["date"]
    date_txt = f"{dd.day} {dd.strftime('%B').upper()} {dd.year}"
    f = font("SemiBold", 25)
    spaced = list(date_txt)
    track = 7 * S
    total = sum(d.textlength(c, font=f) for c in spaced) + track * (len(spaced) - 1)
    x = W * S / 2 - total / 2
    for c in spaced:
        d.text((x, 215 * S), c, font=f, fill=WHITE, anchor="lm")
        x += d.textlength(c, font=f) + track

    # ---- bias pill + subtitle ----
    btxt, bcol = bias_label(ctx)
    _pill(d, PILL_R, 284, btxt, bcol, font("Medium", 23))
    sub = subtitle(ctx)
    d.text((PILL_R * S, 320 * S), sub, font=_fit(d, sub, "Regular", 15, 640), fill=SOFT, anchor="rm")

    # ---- candles ----
    bars = ctx["h1"][-100:]
    price, atr_h = ctx["price"], ctx["atr"]
    res, sup = ctx["res"], ctx["sup"]
    lo, hi = min(b[3] for b in bars), max(b[2] for b in bars)
    span = hi - lo
    levels = [("Resistance", res[1], RED), ("Resistance", res[0], RED),
              ("Support", sup[0], GREEN), ("Support", sup[1], GREEN), ("Support", sup[2], GREEN)]
    shown = []
    for name, z, col in levels:
        mid = (z[0] + z[1]) / 2
        if lo - 0.35 * span <= mid <= hi + 0.35 * span:
            shown.append((name, z, col, mid))
            lo, hi = min(lo, z[0]), max(hi, z[1])
    pad = (hi - lo) * 0.06
    ylo, yhi = lo - pad, hi + pad
    Y = lambda v: PY1 - (v - ylo) / (yhi - ylo) * (PY1 - PY0)

    # grid + price axis
    raw = (yhi - ylo) / 7
    step = next(s for s in (2, 5, 10, 20, 25, 50, 100, 200, 250, 500) if s >= raw)
    v = (int(ylo // step) + 1) * step
    fax = font("Regular", 14)
    while v < yhi:
        y = Y(v)
        d.line(((PX0 * S, y * S), (PX1 * S, y * S)), fill=(255, 255, 255, 16), width=S)
        d.text(((PX1 + 10) * S, y * S), f"{v:,}", font=fax, fill=GREY, anchor="lm")
        v += step
    d.line(((PX1 * S, PY0 * S - 20 * S), (PX1 * S, (PY1 + 12) * S)), fill=(255, 255, 255, 40), width=S)

    n = len(bars)
    slot = (CANDLE_X1 - PX0) / n
    bw = max(2.0, slot * 0.62)
    for i, (t, o, h, l, c) in enumerate(bars):
        cx = PX0 + slot * (i + 0.5)
        col = CANDLE_UP if c >= o else CANDLE_DN
        d.line(((cx * S, Y(h) * S), (cx * S, Y(l) * S)), fill=col, width=max(1, int(1.1 * S)))
        yt, yb = Y(max(o, c)), Y(min(o, c))
        if yb - yt < 1.2:
            yb = yt + 1.2
        d.rectangle(((cx - bw / 2) * S, yt * S, (cx + bw / 2) * S, yb * S), fill=col)

    # day labels (skip the Saturday-morning sliver and crowded labels)
    fdate = font("Regular", 14)
    days, last = [], None
    for i, b in enumerate(bars):
        day = dt.datetime.fromtimestamp(b[0], IST).date()
        if day != last:
            days.append([day, i, 0])
            last = day
        days[-1][2] += 1
    lastx = -999
    for day, i, cnt in days:
        if cnt < 5 or i == 0:
            continue
        x = PX0 + slot * i
        if x - lastx < 70:
            continue
        d.line(((x * S, PY0 * S), (x * S, PY1 * S)), fill=(255, 255, 255, 10), width=S)
        d.text((x * S, 893 * S), day.strftime("%b %-d"), font=fdate, fill=GREY, anchor="mm")
        lastx = x

    # ---- level lines + pills ----
    items = [(mid, f"{name} {zn(z)}", col) for name, z, col, mid in shown]
    items.append((price, f"Current {num(price)}", YEL))
    items.sort(key=lambda t: -t[0])
    ys = [Y(v) for v, _, _ in items]
    gap = 42
    for _ in range(60):
        moved = False
        for i in range(1, len(ys)):
            if ys[i] - ys[i - 1] < gap:
                m = (ys[i] + ys[i - 1]) / 2
                ys[i - 1], ys[i] = m - gap / 2, m + gap / 2
                moved = True
        ys = [min(max(y, PY0 - 5), PY1 - 5) for y in ys]
        if not moved:
            break
    fp = font("Medium", 19)
    for (v, txt, col), py in zip(items, ys):
        tw = d.textlength(txt, font=fp) / S + 28
        left = PILL_R - tw
        ly = Y(v)
        line_col = col[:3] + (210,)
        x_start = 215 if ly > 770 else PX0  # don't run over the 'Smarter Traders' script
        _dashed(d, x_start, left - 6, ly, line_col, dash=9 if col != YEL else 5, gap=6 if col != YEL else 5)
        if abs(py - ly) > 1:
            d.line(((left - 6) * S, ly * S, (left) * S, py * S), fill=line_col, width=int(1.4 * S))
        _pill(d, PILL_R, py, txt, col, fp)

    # ---- scenarios ----
    s0 = sup[0]
    r0 = res[0]
    bt, st = ctx["buy_t"], ctx["sell_t"]
    bull = [f"Hold above {zn(s0)}", f"Break and reclaim {num(ctx['buy_tr'])}",
            f"Next target {num(bt[0])} → {num(bt[1])}"]
    bear = [f"Rejection near {zn(r0)}", f"Loss of {num(ctx['sell_tr'])} weakens buyers",
            f"Below {num(ctx['sell_tr'])} opens {num(st[0])} → {num(st[1])}"]
    for i, y in enumerate((1050, 1100, 1150)):
        d.text((207 * S, y * S), bull[i], font=_fit(d, bull[i], "Medium", 23, 320), fill=WHITE, anchor="lm")
        maxw = 270 if i == 0 else 320
        d.text((675 * S, y * S), bear[i], font=_fit(d, bear[i], "Medium", 23, maxw), fill=WHITE, anchor="lm")

    # ---- footnote ----
    foot = "Levels are approximate; check your broker's live price  •  champmarketlabs.com"
    d.text((W * S / 2, 1365 * S), foot, font=font("Regular", 15), fill=(205, 210, 218, 230), anchor="mm")

    ov = ov.resize((W, H), Image.LANCZOS)
    out = Image.alpha_composite(base, ov).convert("RGB")
    out.save(path, "PNG", optimize=True)
    return open(path, "rb").read()
