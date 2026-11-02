import os, subprocess, sys, datetime as dt

# Scheduled runs: 03:30 UTC (9:00 IST) = market view, 12:30 UTC (6:00 PM IST) = education post.
# Manual runs follow manual_mode.txt: view-dry (default, sends nothing), view-live, edu-live.
if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
    mode = open("manual_mode.txt").read().strip() if os.path.exists("manual_mode.txt") else "view-dry"
else:
    mode = "view-live" if dt.datetime.utcnow().hour < 8 else "edu-live"
env = dict(os.environ)
env["DRY_RUN"] = "1" if mode.endswith("dry") else ""
script = "market_view.py" if mode.startswith("view") else "post_daily.py"
print("mode:", mode, "->", script)
sys.exit(subprocess.call([sys.executable, script], env=env))
