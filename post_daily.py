import os, sys, json, datetime, urllib.request, urllib.parse

START = os.environ.get("START_DATE", "2026-11-03")
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "@Goldtraderchamp")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DRY = os.environ.get("DRY_RUN") == "1"

posts = [p.strip() for p in open("posts.txt", encoding="utf-8").read().split("\n---\n") if p.strip()]
ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
today = datetime.datetime.now(ist).date()
if os.environ.get("FORCE_DATE"):
    today = datetime.date.fromisoformat(os.environ["FORCE_DATE"])
days = (today - datetime.date.fromisoformat(START)).days
if days < 0:
    print("Start date not reached yet."); sys.exit(0)
text = posts[days % len(posts)]
if "champmarketlabs.com" not in text:
    text += "\n\n🌐 champmarketlabs.com"
print(f"Post {days % len(posts) + 1} of {len(posts)} for {today}")
if DRY:
    print(text); sys.exit(0)
if not TOKEN:
    print("Missing TELEGRAM_BOT_TOKEN"); sys.exit(1)
data = urllib.parse.urlencode({"chat_id": CHAT, "text": text, "disable_web_page_preview": "true"}).encode()
req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data)
with urllib.request.urlopen(req, timeout=30) as r:
    res = json.load(r)
print("ok" if res.get("ok") else res)
sys.exit(0 if res.get("ok") else 1)
