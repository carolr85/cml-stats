#!/usr/bin/env python3
"""Champ Market Labs - automatic XAUUSD 'Today's View' post (chart card + caption).

Data: Yahoo gold futures (GC=F) candles, shifted to the live spot price (gold-api.com)
so levels match a broker's XAUUSD. Levels = clustered swing highs/lows, daily highs/lows
and round numbers. Free, no API keys. Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
DRY_RUN=1 (print only), FIXTURE / SPOT / NOW_TS (testing).
"""
import os, sys, json, math, io, time, uuid, textwrap, datetime as dt
import urllib.request, urllib.parse

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "@Goldtraderchamp")
DRY = os.environ.get("DRY_RUN") == "1"
FIX = os.environ.get("FIXTURE")
NOW = int(os.environ.get("NOW_TS") or time.time())
OUT = os.environ.get("CARD_OUT", "card.png")
UA = {"User-Agent": "Mozilla/5.0"}


def http(url, data=None, headers=None, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers or UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # noqa
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"request failed: {url.split('?')[0]}: {last}")


def yahoo(interval, rng):
    if FIX:
        r = json.load(open(FIX))[{"1d": "d", "1h": "h", "15m": "m"}[interval]]
    else:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval={interval}&range={rng}"
        r = json.loads(http(url))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    bars = []
    for t, o, h, l, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"]):
        if None in (o, h, l, c):
            continue
        bars.append([t, o, h, l, c])
    return bars


def get_spot():
    if os.environ.get("SPOT"):
        return float(os.environ["SPOT"])
    return float(json.loads(http("https://api.gold-api.com/price/XAU"))["price"])


# ---------- maths ----------
def ema(vals, n):
    k = 2 / (n + 1)
    out, e = [], vals[0]
    for v in vals:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def atr(bars, n=14):
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i][2], bars[i][3], bars[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    trs = trs[-n:]
    return sum(trs) / len(trs)


def resample(bars, secs):
    out, cur, key = [], None, None
    for t, o, h, l, c in bars:
        k = t // secs
        if k != key:
            if cur:
                out.append(cur)
            cur, key = [t, o, h, l, c], k
        else:
            cur[2] = max(cur[2], h)
            cur[3] = min(cur[3], l)
            cur[4] = c
    if cur:
        out.append(cur)
    return out


def pivots(bars, n):
    pts = []
    for i in range(n, len(bars) - n):
        win = bars[i - n:i + n + 1]
        if bars[i][2] >= max(b[2] for b in win):
            pts.append(bars[i][2])
        if bars[i][3] <= min(b[3] for b in win):
            pts.append(bars[i][3])
    return pts


def trend_label(bars, fast=20, slow=50):
    c = [b[4] for b in bars]
    ef, es = ema(c, fast), ema(c, slow)
    p = c[-1]
    if p < ef[-1] < es[-1]:
        return -1, "bearish"
    if p > ef[-1] > es[-1]:
        return 1, "bullish"
    if p > ef[-1] and ef[-1] < es[-1]:
        return -1, "recovery"  # bounce inside a bigger downtrend
    if p < ef[-1] and ef[-1] > es[-1]:
        return 1, "pullback"  # dip inside a bigger uptrend
    return 0, "range"


def short_label(bars, n=20):
    c = [b[4] for b in bars]
    e = ema(c, n)
    p, rise = c[-1], c[-1] - c[-9]
    if p > e[-1] and e[-1] > e[-4] and rise > 0:
        return 1
    if p < e[-1] and e[-1] < e[-4] and rise < 0:
        return -1
    return 0


# ---------- levels ----------
def build_levels(h1, m15, d1, price, atr_h):
    pts = []  # (price, weight)
    for p in pivots(h1, 3):
        pts.append((p, 1.0))
    for p in pivots(m15, 4):
        pts.append((p, 0.7))
    for b in d1[-6:-1]:
        pts.append((b[2], 2.0))
        pts.append((b[3], 2.0))
    pts.append((d1[-1][2], 1.5))
    pts.append((d1[-1][3], 1.5))
    lo_r, hi_r = price - 6 * atr_h, price + 6 * atr_h
    k = math.ceil(lo_r / 50) * 50
    while k <= hi_r:
        pts.append((float(k), 2.5 if k % 100 == 0 else 1.5))
        k += 50
    pts.sort()
    tol = max(3.0, 0.3 * atr_h)
    clusters = []
    for p, w in pts:
        if clusters and p - clusters[-1]["lo"] <= 2 * tol and p - clusters[-1]["hi"] <= tol:
            c = clusters[-1]
            c["hi"] = p
            c["w"] += w
            c["sum"] += p * w
            c["wt"] += w
        else:
            clusters.append({"lo": p, "hi": p, "w": w, "sum": p * w, "wt": w})
    for c in clusters:
        c["mid"] = c["sum"] / c["wt"]
    return clusters


def zone(c):
    lo, hi = c["lo"], c["hi"]
    if hi - lo < 2.5:
        m = c["mid"]
        lo, hi = m - 1.2, m + 1.2
    lo, hi = int(round(lo)), int(round(hi))
    if hi <= lo:
        hi = lo + 2
    return lo, hi


def pick(clusters, price, atr_h, above):
    buf = 0.2 * atr_h
    if above:
        cs = sorted([c for c in clusters if c["lo"] > price + buf and c["w"] >= 1.5], key=lambda c: c["mid"])
    else:
        cs = sorted([c for c in clusters if c["hi"] < price - buf and c["w"] >= 1.5], key=lambda c: -c["mid"])
    chosen = []
    for c in cs:
        if chosen and abs(c["mid"] - chosen[-1]["mid"]) < 1.0 * atr_h:
            continue
        chosen.append(c)
        if len(chosen) == 3:
            break
    zones = [zone(c) for c in chosen]
    step = int(round(1.3 * atr_h)) or 8
    while len(zones) < 3:  # pad if the chart is too clean
        base = zones[-1] if zones else (int(price), int(price))
        if above:
            lo = base[1] + step
            zones.append((lo, lo + 3))
        else:
            hi = base[0] - step
            zones.append((hi - 3, hi))
    return zones


def fmt(n):
    return f"{int(n):,}"


def zf(z):
    return f"{fmt(z[0])}–{fmt(z[1])}"


# ---------- text ----------
def build_text(ctx):
    p, atr_h = ctx["price"], ctx["atr"]
    res, sup = ctx["res"], ctx["sup"]
    d = ctx["date"]
    s4, l4 = ctx["t4"]
    s1, s15 = ctx["s1"], ctx["s15"]
    z_lo = math.floor(p - 0.35 * atr_h)
    z_hi = math.ceil(p + 0.35 * atr_h)
    z_lo, z_hi = max(z_lo, sup[0][1] + 1), min(z_hi, res[0][0] - 1)
    if z_lo >= z_hi:
        z_lo, z_hi = int(p) - 2, int(p) + 2
    ctx["zone"] = (z_lo, z_hi)

    t4 = {
        "bearish": "The 4H structure remains bearish, with sellers in control",
        "bullish": "The 4H structure remains bullish, with buyers in control",
        "recovery": "The 4H chart shows a corrective recovery inside a broader bearish structure",
        "pullback": "The 4H chart shows a corrective pullback inside a broader bullish structure",
        "range": "The 4H chart is range-bound",
    }[l4]
    t1 = {1: "The 1H trend is bullish", -1: "The 1H chart remains bearish", 0: "The 1H condition is nearly neutral"}[s1]
    t15 = {1: "the 15M chart shows short-term buying pressure",
           -1: "the 15M chart shows short-term selling pressure",
           0: "the 15M chart is consolidating"}[s15]
    para = f"{t4}. {t1}, while {t15}."

    buy_tr, sell_tr = res[0][1], sup[0][0]
    def targets(cands, down):
        out = []
        for v in cands:
            if all(abs(v - o) >= 5 for o in out):
                out.append(v)
        step = max(5, int(round(0.8 * atr_h)))
        while len(out) < 3:
            out.append(out[-1] + (-step if down else step))
        return out[:3]
    sell_t = targets([sup[1][1], sup[2][1], sup[2][0], sup[2][0] - 8], True)
    buy_t = targets([res[1][0], res[1][1], res[2][0], res[2][1], res[2][1] + 8], False)
    ctx.update(buy_tr=buy_tr, sell_tr=sell_tr, buy_t=buy_t, sell_t=sell_t)

    intra = s1 + s15
    if s4 < 0 and intra >= 1:
        bias = f"4H bearish, but intraday recovery is active while {fmt(sup[0][0])} holds."
    elif s4 > 0 and intra <= -1:
        bias = f"4H bullish, but intraday pullback is active while price stays below {fmt(res[0][1])}."
    elif s4 < 0:
        bias = f"Bearish while price remains below {fmt(res[0][1])}. A confirmed hold above {fmt(res[0][1])} would strengthen the bullish case."
    elif s4 > 0:
        bias = f"Bullish while price holds above {fmt(sup[0][0])}. A confirmed break below {fmt(sup[0][0])} would weaken the bullish case."
    elif intra >= 1:
        bias = f"Intraday neutral-to-bullish while price holds above {fmt(sup[0][0])}."
    elif intra <= -1:
        bias = f"Intraday neutral-to-bearish while price remains below {fmt(res[0][1])}."
    else:
        bias = f"Neutral between {fmt(sup[0][0])} and {fmt(res[0][1])}. Avoid entering in the middle of the range."
    ctx["bias"] = bias

    event = ""
    if d.weekday() == 4 and d.day <= 7:
        event = "US employment data is scheduled today. Expect strong volatility and possible false breakouts.\n"

    lines = [
        "📊 XAUUSD — Today's View",
        f"📅 {d.day} {d.strftime('%B %Y')}",
        f"Gold is trading near {fmt(round(p))}, inside the current zone of {fmt(z_lo)}–{fmt(z_hi)}.",
        para,
        f"🔴 Resistance: {zf(res[0])}",
        f"🔴 Major resistance: {zf(res[1])}",
        f"🟢 Support: {zf(sup[0])}",
        f"🟢 Intraday support: {zf(sup[1])}",
        f"🟢 Major support: {zf(sup[2])}",
        f"📉 Below {fmt(sell_tr)} with confirmation, sellers may target {fmt(sell_t[0])}, {fmt(sell_t[1])} and {fmt(sell_t[2])}.",
        f"📈 Above {fmt(buy_tr)} with confirmation, buyers may target {fmt(buy_t[0])}, {fmt(buy_t[1])} and {fmt(buy_t[2])}.",
        f"Bias: {bias}",
        event + "⏳ Wait for a confirmed breakout, retest or clear rejection before entering.",
        "Levels are approximate; check your broker's live price.",
        "Educational only • Manage risk",
    ]
    return "\n".join(l.rstrip("\n") for l in lines)


# ---------- chart card ----------
def make_card(ctx, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    NAVY, PANEL, GOLD = "#0b1424", "#13203a", "#d4af37"
    RED, GREEN, GREY, WHITE = "#e74c3c", "#2ecc71", "#8a97ad", "#f2f4f8"
    W, H = 1080, 1350
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=NAVY)
    bg = fig.add_axes([0, 0, 1, 1])
    bg.set_xlim(0, W)
    bg.set_ylim(H, 0)
    bg.axis("off")
    bg.add_patch(Rectangle((0, 0), W, 8, color=GOLD))
    bg.add_patch(Rectangle((0, H - 8), W, 8, color=GOLD))

    logo = ctx.get("logo")
    if logo and os.path.exists(logo):
        ax = fig.add_axes([60 / W, 1 - 190 / H, 130 / W, 130 / H])
        ax.imshow(plt.imread(logo))
        ax.axis("off")
    bg.text(215, 95, "TODAY'S MARKET VIEW", color=GOLD, fontsize=31, fontweight="bold", va="center")
    d = ctx["date"]
    bg.text(215, 150, f"XAUUSD  •  {d.day} {d.strftime('%B %Y')}", color=WHITE, fontsize=19, va="center")
    bg.text(W - 60, 95, fmt(round(ctx["price"])), color=WHITE, fontsize=31, fontweight="bold", ha="right", va="center")
    bg.text(W - 60, 150, "Gold now", color=GREY, fontsize=15, ha="right", va="center")

    # chart
    bars = ctx["h1"][-96:]
    cy0, cy1 = 215, 840
    ax = fig.add_axes([60 / W, 1 - cy1 / H, (W - 120) / W, (cy1 - cy0) / H], facecolor=PANEL)
    atr_h, price = ctx["atr"], ctx["price"]
    wlo, whi = min(b[3] for b in bars), max(b[2] for b in bars)
    lo, hi = wlo, whi
    for z in (ctx["res"][0], ctx["res"][1], ctx["sup"][0], ctx["sup"][1]):
        if abs((z[0] + z[1]) / 2 - price) < 4 * atr_h:
            lo, hi = min(lo, z[0]), max(hi, z[1])
    pad = 0.6 * atr_h
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xlim(-1, len(bars) + 14)
    for i, (t, o, h, l, c) in enumerate(bars):
        col = GREEN if c >= o else RED
        ax.vlines(i, l, h, color=col, linewidth=1.2)
        ax.bar(i, max(abs(c - o), 0.15), bottom=min(o, c), width=0.62, color=col)
    ylo, yhi = ax.get_ylim()
    tr = ax.get_yaxis_transform()
    for tag, z, col in (("R1", ctx["res"][0], RED), ("R2", ctx["res"][1], RED),
                        ("S1", ctx["sup"][0], GREEN), ("S2", ctx["sup"][1], GREEN)):
        if z[1] < ylo or z[0] > yhi:
            continue
        ax.axhspan(z[0], z[1], color=col, alpha=0.20, linewidth=0)
        ax.text(0.995, (z[0] + z[1]) / 2, f"{tag}  {zf(z)}", transform=tr, color=col, fontsize=12.5,
                fontweight="bold", ha="right", va="center")
    ax.axhline(price, color=GOLD, linestyle="--", linewidth=1.2)
    ax.text(0.01, price, f" {price:,.1f}", transform=tr, color=NAVY, fontsize=12, fontweight="bold",
            va="bottom", bbox=dict(boxstyle="round,pad=0.2", fc=GOLD, ec=GOLD))
    # x ticks = start of each IST day
    ticks, labels, last = [], [], None
    for i, b in enumerate(bars):
        day = dt.datetime.fromtimestamp(b[0], IST)
        if day.date() != last:
            if last is not None:
                ticks.append(i)
                labels.append(day.strftime("%a %d"))
            last = day.date()
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, color=GREY, fontsize=12)
    ax.tick_params(axis="y", colors=GREY, labelsize=12)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.grid(color="#22304d", linewidth=0.6)
    for s in ax.spines.values():
        s.set_color("#22304d")
    bg.text(60, cy1 + 62, "1H chart • last 4 sessions", color=GREY, fontsize=12, va="center")

    # scenario boxes
    by0, bh = 905, 215
    for x0, title, col, trig, tg in (
            (60, f"BEARISH BELOW {fmt(ctx['sell_tr'])}", RED, "Sellers may target", ctx["sell_t"]),
            (555, f"BULLISH ABOVE {fmt(ctx['buy_tr'])}", GREEN, "Buyers may target", ctx["buy_t"])):
        bg.add_patch(Rectangle((x0, by0), 465, bh, facecolor=PANEL, edgecolor=col, linewidth=2))
        bg.text(x0 + 232, by0 + 55, title, color=col, fontsize=19, fontweight="bold", ha="center", va="center")
        bg.text(x0 + 232, by0 + 112, trig, color=GREY, fontsize=14, ha="center", va="center")
        bg.text(x0 + 232, by0 + 160, "  →  ".join(fmt(v) for v in tg), color=WHITE, fontsize=19,
                fontweight="bold", ha="center", va="center")
    # bias
    bias = "\n".join(textwrap.wrap("Bias: " + ctx["bias"], 62)[:3])
    bg.text(W / 2, 1190, bias, color=WHITE, fontsize=15.5, ha="center", va="center", linespacing=1.5)
    bg.add_patch(Rectangle((60, 1245, ), W - 120, 58, color=GOLD))
    bg.text(W / 2, 1274, "WAIT FOR CONFIRMATION", color=NAVY, fontsize=20, fontweight="bold", ha="center", va="center")
    bg.text(W / 2, 1328, "champmarketlabs.com  •  Educational only  •  Manage risk", color=GREY, fontsize=12.5,
            ha="center", va="center")
    fig.savefig(path, facecolor=NAVY)
    plt.close(fig)
    return open(path, "rb").read()


# ---------- telegram ----------
def send_photo(png, caption):
    b = uuid.uuid4().hex
    parts = []
    for n, v in (("chat_id", CHAT), ("caption", caption)):
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="view.png"\r\n'
                 f'Content-Type: image/png\r\n\r\n'.encode())
    parts.append(png)
    parts.append(f"\r\n--{b}--\r\n".encode())
    return http(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", data=b"".join(parts),
                headers={"Content-Type": f"multipart/form-data; boundary={b}"}, tries=1)


def send_message(text):
    data = urllib.parse.urlencode({"chat_id": CHAT, "text": text, "disable_web_page_preview": "true"}).encode()
    return http(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data, tries=1)


def main():
    now = dt.datetime.fromtimestamp(NOW, IST)
    if now.weekday() >= 5:
        print("Weekend (IST) - gold market closed, no post.")
        return 0
    d1 = yahoo("1d", "2mo")
    h1 = yahoo("1h", "10d")
    m15 = yahoo("15m", "3d")
    if NOW - m15[-1][0] > 3 * 3600 and not FIX:
        print("Latest candle is more than 3h old - market closed/holiday, no post.")
        return 0
    spot = get_spot()
    basis = spot - m15[-1][4]
    print(f"spot {spot:.1f}, futures {m15[-1][4]:.1f}, basis {basis:+.1f}")
    if abs(basis) > 40:
        print("Basis looks wrong - refusing to post.")
        return 1
    for arr in (d1, h1, m15):
        for b in arr:
            for i in (1, 2, 3, 4):
                b[i] += basis
    price = spot
    atr_h = atr(h1, 14)
    clusters = build_levels(h1, m15, d1, price, atr_h)
    res = pick(clusters, price, atr_h, True)
    sup = pick(clusters, price, atr_h, False)
    ctx = dict(price=price, atr=atr_h, res=res, sup=sup, date=now.date(), h1=h1,
               t4=trend_label(resample(h1, 4 * 3600)), s1=short_label(h1), s15=short_label(m15),
               logo=os.path.join(os.path.dirname(os.path.abspath(__file__)), "cml-logo.png"))
    ctx["date"] = dt.date(now.year, now.month, now.day)
    caption = build_text(ctx)
    png = make_card(ctx, OUT)
    print(caption)
    print(f"\n[caption {len(caption)} chars, card {len(png)} bytes]")
    if DRY:
        print("DRY RUN - nothing sent.")
        return 0
    if not TOKEN:
        print("No TELEGRAM_BOT_TOKEN set.")
        return 1
    if len(caption) <= 1000:
        send_photo(png, caption)
    else:
        head, rest = caption.split("\n", 2)[0:2], caption.split("\n", 2)[2]
        send_photo(png, "\n".join(head))
        send_message(rest)
    print("Posted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
