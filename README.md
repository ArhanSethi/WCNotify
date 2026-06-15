# WCNotify

I like knowing what's going on in the World Cup, but I'm too lazy to actually watch, and I always forget to check the score. This script runs in the background and throws a simple Windows notification whenever something happens in a game.

## What it notifies you about

- Kickoff
- Goals (with score)
- Red cards
- Half time / second half
- Extra time
- Penalty shootout
- Final whistle + winner

## Setup

```
pip install requests winotify
python wc_notify.py
```

Leave the terminal open in the background.

## Notes

- Uses ESPN's public API
- Polls every 45 seconds, so notifications may be slightly delayed
- Covers all WC26 Games
