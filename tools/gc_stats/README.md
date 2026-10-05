# GameChanger box-score stats

Scrapes every completed game's box score for one or more GameChanger teams and
adds up the batting stats per player and per team.

It runs a Chrome window on your own computer. Box scores are only visible when
signed in, so the first run asks you to sign in to GameChanger in that window.
The login is saved in a local profile folder (`~/.gc-scraper-profile`), so later
runs don't ask again. Your password never leaves your computer.

## Setup (once)

```bash
cd tools/gc_stats
pip install -r requirements.txt
playwright install chromium   # only needed if Google Chrome isn't installed
```

## Run

One team:

```bash
python gc_boxscores.py "https://web.gc.com/teams/7tYhI2eIzIOj/2027-summer-turnin2-pezz-national-16u/schedule"
```

Several teams: put one URL per line in a file (see `teams.example.txt`):

```bash
python gc_boxscores.py --teams-file teams.txt
```

The first time, a Chrome window opens. Sign in to GameChanger there, then press
Enter in the terminal.

## If GameChanger won't let you sign in

GameChanger (and Google sign-in) can block sign-in in a browser that a script
opened. Instead, start Chrome yourself, sign in normally, then let the script
attach to it.

1. Quit Chrome completely (Cmd+Q on a Mac).
2. Start Chrome with remote control turned on, using its own profile folder:

   **Mac**
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="$HOME/gc-chrome"
   ```
   **Windows**
   ```bat
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\gc-chrome"
   ```
3. In that Chrome window, go to web.gc.com, sign in, and check that a box
   score shows real numbers.
4. In a second Terminal window:
   ```bash
   cd tools/gc_stats
   source .venv/bin/activate
   python gc_boxscores.py --cdp http://localhost:9222 --teams-file teams.txt
   ```

Your sign-in is kept in the `gc-chrome` folder, so next time you only repeat
steps 2 and 4. Close that Chrome window when you're done: while it's open with
remote control on, other programs on your computer can control it.

## Output (in `stats_out/`)

| File | Contents |
|---|---|
| `<team>_batting_totals.csv` | One row per player plus a TEAM row: G, AB, R, H, 1B, 2B, 3B, HR, RBI, BB, SO, HBP, SB, CS, SF, SAC, TB, AVG, OBP, SLG, OPS |
| `<team>_batting_by_game.csv` | Every player's line from every game |
| `all_teams_batting_totals.csv` | All teams' totals in one file |

Each game's player runs are checked against the final score. Any game that
doesn't match, or couldn't be read, is listed under **Warnings** at the end.

## Notes

- OBP = (H + BB + HBP) / (AB + BB + HBP + SF). If a box score doesn't list
  sacrifice flies, OBP may be slightly high.
- 2B, 3B, HR, HBP, SB and so on come from the lines under each box score table.
- If box scores still look blurred after signing in, the account doesn't have
  access to that team (a fan subscription or team invite is needed).
