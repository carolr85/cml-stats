"""Reads the public MQL5 signal page and writes stats.json for champmarketlabs.com.
Only standard library. Keeps the old file if anything looks wrong."""
import json, re, sys, urllib.request
from datetime import datetime, timezone, timedelta

URL = "https://www.mql5.com/en/signals/2385188"
OUT = "stats.json"

req = urllib.request.Request(URL, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})
html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")


def num(s):
    return float(s.replace(" ", "").replace(" ", "").replace(",", ""))


def label_value(label):
    m = re.search(r'__label">\s*' + re.escape(label) + r'\s*</div>\s*<div class="s-[\w-]+__value">\s*(?:<i[^>]*>)?\s*([^<]+?)\s*<',
                  html)
    return m.group(1).strip() if m else None


growth = label_value("Growth:")
weeks = label_value("Weeks:")
monthly = label_value("Monthly growth:")
trades = label_value("Trades:")
m = re.search(r"value:([\d.]+),name:'Profit Trades'", html)
win = float(m.group(1)) if m else None
if win is None:
    pt = label_value("Profit Trades:")
    mm = re.search(r"\(([\d.]+)%\)", pt or "")
    win = round(float(mm.group(1)), 1) if mm else None

# growth curve: window.growthChart(...,{...},[[x,y,x,y,...]])
eq = []
i = html.find("window.growthChart(")
if i >= 0:
    j = html.find("[[", i)
    k = html.find("]", j)
    vals = [v for v in html[j + 2:k].split(",") if v.strip()]
    ys = [float(v) for v in vals[1::2]]
    if len(ys) > 2:
        step = max(1, len(ys) // 120)
        eq = ys[::step]
        if eq[-1] != ys[-1]:
            eq.append(ys[-1])

try:
    g = num(growth.rstrip("%"))
    mo = num(monthly.rstrip("%"))
    w = int(num(weeks))
    t = int(num(trades))
    assert win is not None
except Exception as e:  # page changed or blocked: keep last good numbers
    print("Could not read MQL5 page:", e, growth, weeks, monthly, trades, win)
    sys.exit(1)

ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
data = {
    "growth": f"{'+' if g >= 0 else ''}{g:.2f}%",
    "weeks": f"{w} wks",
    "monthly": f"{'+' if mo >= 0 else ''}{mo:.2f}%",
    "winrate": f"{win:.1f}%",
    "trades": f"{t:,}",
    "updated": ist.strftime("%-d %b %Y"),
    "equity": [round(v, 2) for v in eq],
}
json.dump(data, open(OUT, "w"), indent=1)
print("Updated", data["growth"], data["weeks"], data["monthly"], data["winrate"], data["trades"], len(eq))
