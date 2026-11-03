import os, json, subprocess, sys, datetime as dt

# The workflow wakes up every 30 minutes (GitHub's free timer is often late or skips runs).
# Each wake-up posts whatever is due today and not yet sent, then remembers it in posted.json:
#   market view  -> from 09:00 IST until 13:59 IST
#   education    -> from 18:00 IST until 23:59 IST
# A late run therefore never sends the wrong post at the wrong hour, and nothing is posted twice.
# Manual runs: pick a mode when you press "Run workflow" (default view-dry = sends nothing).
#   auto = same as the timer, view-live / edu-live = send now, view-dry / edu-dry = test only.

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
STATE = "posted.json"
SLOTS = {  # name: (script, start hour, end hour exclusive, hour of the last try)
    "view": ("market_view.py", 9, 14, 13),
    "edu": ("post_daily.py", 18, 24, 23),
}


def load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save(state):
    with open(STATE, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def run(name, dry):
    env = dict(os.environ)
    env["DRY_RUN"] = "1" if dry else ""
    print(f"-> {name} ({'dry' if dry else 'live'})")
    return subprocess.call([sys.executable, SLOTS[name][0]], env=env)


def main():
    now = dt.datetime.now(IST)
    today = now.date().isoformat()
    state = load()
    mode = "auto"
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        mode = (os.environ.get("RUN_MODE") or "").strip()
        if not mode and os.path.exists("manual_mode.txt"):
            mode = open("manual_mode.txt").read().strip()
        mode = mode or "view-dry"
    print("IST now:", now.strftime("%Y-%m-%d %H:%M"), "| mode:", mode, "| already posted:", state)

    if mode != "auto":
        name, kind = mode.split("-")
        code = run(name, kind == "dry")
        if code == 0 and kind == "live":
            state[name] = today
            save(state)
        return code

    for name, (script, start, end, last) in SLOTS.items():
        if not (start <= now.hour < end):
            continue
        if state.get(name) == today:
            print(f"{name}: already posted today - nothing to do.")
            continue
        code = run(name, False)
        if code == 0:
            state[name] = today
            save(state)
        else:
            print(f"{name}: failed - will try again on the next run.")
            if now.hour >= last:
                return code  # last chance of the day: show a red failed run
        return 0
    print("Nothing due right now.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
