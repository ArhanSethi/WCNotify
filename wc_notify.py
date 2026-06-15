#!/usr/bin/env python3
"""
World Cup 2026 live notifier
Polls ESPN's public API and fires Windows toast notifications for game events.

Install deps: pip install requests winotify
Run: python wc_notify.py
"""

import time
import requests
from datetime import datetime

try:
    from winotify import Notification, audio
    NOTIF_BACKEND = "winotify"
except ImportError:
    NOTIF_BACKEND = "fallback"
    import subprocess

POLL_INTERVAL = 45  # seconds -- ESPN updates roughly this fast
API_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
APP_ID = "World Cup 2026"

# Tracks last known state per game id
state: dict = {}


# ── Notification ──────────────────────────────────────────────────────────────

def notify(title: str, body: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {title} | {body}")

    if NOTIF_BACKEND == "winotify":
        toast = Notification(
            app_id=APP_ID,
            title=title,
            msg=body,
            duration="short",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    else:
        # PowerShell balloon fallback (no extra deps)
        safe_title = title.replace('"', "'")
        safe_body = body.replace('"', "'")
        ps = (
            'Add-Type -AssemblyName System.Windows.Forms;'
            '$n = New-Object System.Windows.Forms.NotifyIcon;'
            '$n.Icon = [System.Drawing.SystemIcons]::Information;'
            '$n.Visible = $True;'
            f'$n.ShowBalloonTip(8000, "{safe_title}", "{safe_body}", '
            '[System.Windows.Forms.ToolTipIcon]::Info);'
            'Start-Sleep -Seconds 8;'
            '$n.Dispose()'
        )
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )


# ── ESPN API ──────────────────────────────────────────────────────────────────

def fetch_games() -> list:
    try:
        r = requests.get(API_URL, timeout=10)
        r.raise_for_status()
        return r.json().get("events", [])
    except requests.RequestException as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] fetch error: {e}")
        return []


def parse_game(event: dict) -> dict:
    comp = event.get("competitions", [{}])[0]
    competitors = comp.get("competitors", [])

    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})

    home_name = home.get("team", {}).get("abbreviation", "?")
    away_name = away.get("team", {}).get("abbreviation", "?")
    home_full = home.get("team", {}).get("displayName", home_name)
    away_full = away.get("team", {}).get("displayName", away_name)

    home_score = int(home.get("score") or 0)
    away_score = int(away.get("score") or 0)

    status_obj = comp.get("status", {})
    status_name = status_obj.get("type", {}).get("name", "")
    clock = status_obj.get("displayClock", "")
    period = int(status_obj.get("period") or 0)

    # Pull play-by-play details if available for card detection
    details = comp.get("details", [])
    red_cards = [
        d for d in details
        if d.get("type", {}).get("text", "").lower() in ("red card", "yellow-red card")
    ]

    return {
        "id": event.get("id"),
        "home": home_name,
        "away": away_name,
        "home_full": home_full,
        "away_full": away_full,
        "home_score": home_score,
        "away_score": away_score,
        "status": status_name,
        "clock": clock,
        "period": period,
        "red_card_count": len(red_cards),
        "last_play": comp.get("lastPlay", {}).get("text", ""),
    }


# ── Event detection ───────────────────────────────────────────────────────────

def score_str(g: dict) -> str:
    return f"{g['home']} {g['home_score']} - {g['away_score']} {g['away']}"


def check_and_notify(prev: dict, curr: dict):
    matchup = f"{curr['home_full']} vs {curr['away_full']}"
    ps = prev.get("status", "")
    cs = curr["status"]

    # --- Kickoff ---
    if ps not in ("STATUS_IN_PROGRESS",) and cs == "STATUS_IN_PROGRESS" and curr["period"] == 1:
        notify("⚽  Kickoff!", matchup)

    # --- Goal ---
    prev_total = prev.get("home_score", 0) + prev.get("away_score", 0)
    curr_total = curr["home_score"] + curr["away_score"]
    if curr_total > prev_total:
        if curr["home_score"] > prev.get("home_score", 0):
            notify(f"⚽  GOAL! {curr['home_full']}", score_str(curr))
        elif curr["away_score"] > prev.get("away_score", 0):
            notify(f"⚽  GOAL! {curr['away_full']}", score_str(curr))
        else:
            notify("⚽  GOAL!", score_str(curr))

    # --- Red card (count increased) ---
    if curr["red_card_count"] > prev.get("red_card_count", 0):
        notify("🟥  Red Card!", f"{matchup} | {score_str(curr)}")

    # --- Half time ---
    if ps == "STATUS_IN_PROGRESS" and cs == "STATUS_HALFTIME":
        notify("⏸  Half Time", f"{score_str(curr)}")

    # --- Second half ---
    if ps == "STATUS_HALFTIME" and cs == "STATUS_IN_PROGRESS":
        notify("▶️  Second Half", matchup)

    # --- Extra time starts ---
    if prev.get("period", 0) < 3 and curr["period"] == 3 and cs == "STATUS_IN_PROGRESS":
        notify("⏱  Extra Time", f"{matchup} | {score_str(curr)}")

    # --- Penalties ---
    if ps != "STATUS_SHOOTOUT" and cs == "STATUS_SHOOTOUT":
        notify("🎯  Penalty Shootout!", matchup)

    # --- Full time ---
    if ps in ("STATUS_IN_PROGRESS", "STATUS_SHOOTOUT") and cs == "STATUS_FINAL":
        hs, as_ = curr["home_score"], curr["away_score"]
        if hs > as_:
            result = f"{curr['home_full']} wins!"
        elif as_ > hs:
            result = f"{curr['away_full']} wins!"
        else:
            result = "Draw!"
        notify("🏁  Full Time", f"{score_str(curr)} — {result}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    print(f"World Cup 2026 notifier — polling every {POLL_INTERVAL}s")
    print(f"Notification backend: {NOTIF_BACKEND}")
    if NOTIF_BACKEND == "fallback":
        print("  Tip: pip install winotify  for proper toast notifications\n")
    print("Press Ctrl+C to stop.\n")

    # Seed state without firing notifications
    for event in fetch_games():
        g = parse_game(event)
        state[g["id"]] = g
        status_label = g["status"].replace("STATUS_", "").replace("_", " ").title()
        print(f"  Tracking: {g['home_full']} vs {g['away_full']} [{status_label}]")

    if not state:
        print("  No games found right now — will keep checking for new ones.")

    print()

    while True:
        time.sleep(POLL_INTERVAL)
        games = fetch_games()

        for event in games:
            curr = parse_game(event)
            gid = curr["id"]
            prev = state.get(gid, {})

            if not prev:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] New game: {curr['home_full']} vs {curr['away_full']}")

            check_and_notify(prev, curr)
            state[gid] = curr

        # Print live game status to terminal
        live = [g for g in state.values() if g["status"] == "STATUS_IN_PROGRESS"]
        for g in live:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {score_str(g)}  {g['clock']}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
