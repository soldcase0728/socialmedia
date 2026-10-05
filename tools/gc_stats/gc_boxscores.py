#!/usr/bin/env python3
"""Scrape and aggregate GameChanger box-score batting stats for one or more teams.

Runs a real Chrome window on your own computer. The first time, sign in to
GameChanger in that window; the login is kept in a local profile folder so
later runs don't ask again. Your credentials never leave your machine.

Usage:
    python gc_boxscores.py URL [URL ...] [--out stats_out]
    python gc_boxscores.py --teams-file teams.txt

Each URL is any web.gc.com team page, e.g.
    https://web.gc.com/teams/7tYhI2eIzIOj/2027-summer-turnin2-pezz-national-16u/schedule
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError

API = "https://api.team-manager.gc.com/public"
TEAM_URL_RE = re.compile(r"web\.gc\.com/teams/([A-Za-z0-9]+)/([^/?#]+)")

# Counting stats summed across games. Table columns come first, then the
# "extra" lines GameChanger prints under each lineup (e.g. "2B: J Doe 2").
TABLE_STATS = ["AB", "R", "H", "RBI", "BB", "SO"]
EXTRA_STATS = ["2B", "3B", "HR", "TB", "HBP", "SB", "CS", "SF", "SAC", "E"]
OUTPUT_STATS = ["G", "AB", "R", "H", "1B", "2B", "3B", "HR", "RBI", "BB", "SO",
                "HBP", "SB", "CS", "SF", "SAC", "TB", "AVG", "OBP", "SLG", "OPS"]

# Runs in the page and returns both teams' batting tables plus extra lines.
EXTRACT_JS = r"""
() => {
  const side = (s) => {
    const nameEl = document.querySelector(`.BoxScore__${s}TeamName`);
    const lineup = document.querySelector(`.BoxScore__${s}Lineup`);
    if (!lineup) return null;
    const rows = {};
    lineup.querySelectorAll('.ag-row').forEach(row => {
      const key = row.getAttribute('row-id') + '|' + (row.closest('.ag-floating-bottom') ? 'f' : 'b');
      const rec = rows[key] || (rows[key] = {});
      row.querySelectorAll('[col-id]').forEach(cell => {
        const col = cell.getAttribute('col-id');
        if (col === 'player') {
          const n = cell.querySelector('.BoxScoreComponents__playerName');
          const i = cell.querySelector('.BoxScoreComponents__playerInfo');
          rec.name = (n ? n.textContent : cell.textContent).trim();
          rec.info = i ? i.textContent.trim() : '';
        } else {
          rec[col] = cell.textContent.trim();
        }
      });
    });
    const extras = {};
    const extraBox = document.querySelector(`.BoxScore__${s}LineupExtra`);
    if (extraBox) {
      extraBox.querySelectorAll(':scope > div').forEach(line => {
        const label = (line.querySelector('.Text__semibold') || {}).textContent || '';
        const vals = [...line.querySelectorAll('.BoxScoreComponents__extraPlayerStat')]
          .map(e => e.textContent.trim());
        if (label) extras[label.replace(':', '').trim()] = vals;
      });
    }
    return {team: nameEl ? nameEl.textContent.trim() : '', rows: Object.values(rows), extras};
  };
  return {
    blurred: document.querySelectorAll('.BoxScore__blurred').length,
    away: side('away'),
    home: side('home'),
  };
}
"""


def num(v) -> int:
    try:
        return int(str(v).strip() or 0)
    except ValueError:
        return 0


def norm(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


def parse_extras(extras: dict[str, list[str]]) -> dict[str, dict[str, int]]:
    """{'HR': ['K Redmond 2,', 'A Doe']} -> {'k redmond': {'HR': 2}, 'a doe': {'HR': 1}}"""
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for label, entries in extras.items():
        stat = label.upper()
        if stat not in EXTRA_STATS:
            continue
        for entry in entries:
            for part in entry.split(","):
                part = part.strip()
                if not part:
                    continue
                m = re.match(r"^(.*?)(?:\s+(\d+))?$", part)
                name, count = m.group(1), int(m.group(2) or 1)
                out[norm(name)][stat] = out[norm(name)].get(stat, 0) + count
    return out


def game_lines(side: dict) -> list[dict]:
    """Per-player stat lines for one team in one game (TEAM total row dropped)."""
    extras = parse_extras(side["extras"])
    lines = []
    for row in side["rows"]:
        name = row.get("name", "")
        if not name or name.upper() == "TEAM":
            continue
        line = {"name": name, "info": row.get("info", "")}
        for s in TABLE_STATS:
            line[s] = num(row.get(s))
        for s in EXTRA_STATS:
            line[s] = extras.get(norm(name), {}).get(s, 0)
        lines.append(line)
    return lines


def rate_stats(t: dict) -> dict:
    t["1B"] = t["H"] - t["2B"] - t["3B"] - t["HR"]
    t["TB"] = t["1B"] + 2 * t["2B"] + 3 * t["3B"] + 4 * t["HR"]
    ab, pa_obp = t["AB"], t["AB"] + t["BB"] + t["HBP"] + t["SF"]
    t["AVG"] = t["H"] / ab if ab else 0.0
    t["OBP"] = (t["H"] + t["BB"] + t["HBP"]) / pa_obp if pa_obp else 0.0
    t["SLG"] = t["TB"] / ab if ab else 0.0
    t["OPS"] = t["OBP"] + t["SLG"]
    return t


def fmt(v) -> str:
    return f"{v:.3f}".lstrip("0") if isinstance(v, float) else str(v)


def pick_side(data: dict, team_name: str, home_away: str) -> dict | None:
    for s in ("away", "home"):
        if data.get(s) and norm(data[s]["team"]) == norm(team_name):
            return data[s]
    return data.get(home_away) if home_away in ("away", "home") else None


def load_box_score(page: Page, url: str) -> dict:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector(".BoxScore__awayLineup .ag-row", timeout=30000)
    page.wait_for_timeout(1000)  # let both grids finish rendering
    return page.evaluate(EXTRACT_JS)


def live_page(ctx: BrowserContext, page: Page) -> Page:
    """Return an open tab, opening a new one if the user closed ours."""
    if not page.is_closed():
        return page
    open_pages = [pg for pg in ctx.pages if not pg.is_closed()]
    return open_pages[-1] if open_pages else ctx.new_page()


def ensure_signed_in(ctx: BrowserContext, page: Page, url: str) -> Page:
    data = load_box_score(page, url)
    while data["blurred"]:
        print("\nBox scores are blurred, so you're not signed in yet.")
        print("1. Sign in to GameChanger in the Chrome window this script is using.")
        print("   Leave that window open when you're done (don't close or quit it).")
        answer = input("2. Come back here and press Enter (or type q to quit): ")
        if answer.strip().lower() == "q":
            sys.exit("Stopped.")
        try:
            page = live_page(ctx, page)
            data = load_box_score(page, url)
        except PlaywrightError as e:
            if "closed" in str(e).lower():
                sys.exit("The Chrome window was closed. Run the script again; "
                         "if you finished signing in, it will remember you.")
            raise
        if data["blurred"]:
            print("Still blurred. Make sure the sign-in finished, then try again.\n"
                  "(If it stays blurred, this account can't see these box scores.)")
    return page


def scrape_team(ctx: BrowserContext, page: Page, team_url: str, delay: float):
    m = TEAM_URL_RE.search(team_url)
    if not m:
        print(f"Skipping (not a web.gc.com team URL): {team_url}")
        return None
    team_id, slug = m.groups()
    team = ctx.request.get(f"{API}/teams/{team_id}").json()
    games = ctx.request.get(f"{API}/teams/{team_id}/games").json()
    done = [g for g in games if g.get("game_status") == "completed"]
    done.sort(key=lambda g: g.get("start_ts", ""))
    print(f"\n== {team['name']}: {len(done)} completed games")

    base = f"https://web.gc.com/teams/{team_id}/{slug}/schedule"
    if done:
        page = ensure_signed_in(ctx, page, f"{base}/{done[0]['id']}/box-score")

    by_game, warnings = [], []
    for g in done:
        opp = g["opponent_team"]["name"]
        date = g.get("start_ts", "")[:10]
        label = f"{date} {'@' if g.get('home_away') == 'away' else 'vs.'} {opp}"
        try:
            page = live_page(ctx, page)
            data = load_box_score(page, f"{base}/{g['id']}/box-score")
        except Exception as e:  # noqa: BLE001 - report and keep going
            warnings.append(f"{label}: could not load box score ({e.__class__.__name__})")
            continue
        if data["blurred"]:
            warnings.append(f"{label}: box score blurred (signed out?), skipped")
            continue
        side = pick_side(data, team["name"], g.get("home_away", ""))
        if not side:
            warnings.append(f"{label}: couldn't find {team['name']} in the box score")
            continue
        lines = game_lines(side)
        runs, final = sum(l["R"] for l in lines), g.get("score", {}).get("team")
        status = "ok" if final is None or runs == final else f"MISMATCH (box {runs} R vs final {final})"
        if status != "ok":
            warnings.append(f"{label}: {status}")
        print(f"  {label:<60} {g['score']['team']}-{g['score']['opponent_team']}  {status}")
        for l in lines:
            by_game.append({"date": date, "opponent": opp, "game_id": g["id"], **l})
        time.sleep(delay)
    return team, slug, by_game, warnings, page


def aggregate(by_game: list[dict]) -> list[dict]:
    totals: dict[str, dict] = {}
    for l in by_game:
        key = norm(l["name"])
        t = totals.setdefault(key, {"name": l["name"], "number": "", "games": set(),
                                    **{s: 0 for s in TABLE_STATS + EXTRA_STATS}})
        num_m = re.search(r"#(\d+)", l.get("info", ""))
        if num_m and not t["number"]:
            t["number"] = num_m.group(1)
        t["games"].add(l["game_id"])
        for s in TABLE_STATS + EXTRA_STATS:
            t[s] += l[s]
    rows = []
    for t in totals.values():
        t["G"] = len(t.pop("games"))
        rows.append(rate_stats(t))
    rows.sort(key=lambda r: (-r["OPS"], r["name"]))
    team = {"name": "TEAM", "number": "", "G": max((r["G"] for r in rows), default=0),
            **{s: sum(r[s] for r in rows) for s in TABLE_STATS + EXTRA_STATS}}
    return rows + [rate_stats(team)]


def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([fmt(r.get(c, "")) for c in cols])


def print_table(team_name: str, rows: list[dict]) -> None:
    cols = ["G", "AB", "R", "H", "2B", "3B", "HR", "RBI", "BB", "SO", "HBP", "SB", "AVG", "OBP", "SLG", "OPS"]
    print(f"\n{team_name}")
    print(f"{'Player':<22}" + "".join(f"{c:>6}" for c in cols))
    for r in rows:
        print(f"{r['name'][:22]:<22}" + "".join(f"{fmt(r[c]):>6}" for c in cols))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*", help="web.gc.com team URLs")
    ap.add_argument("--teams-file", help="text file with one team URL per line")
    ap.add_argument("--out", default="stats_out", help="output folder (default: stats_out)")
    ap.add_argument("--profile", default=str(Path.home() / ".gc-scraper-profile"),
                    help="Chrome profile folder that keeps your GameChanger login")
    ap.add_argument("--cdp", metavar="URL",
                    help="attach to a Chrome you started yourself, e.g. http://localhost:9222")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds to wait between games")
    args = ap.parse_args()

    urls = list(args.urls)
    if args.teams_file:
        urls += [u.strip() for u in Path(args.teams_file).read_text().splitlines()
                 if u.strip() and not u.lstrip().startswith("#")]
    if not urls:
        ap.error("give at least one team URL or --teams-file")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cols = ["name", "number"] + OUTPUT_STATS
    game_cols = ["date", "opponent", "name", "info"] + TABLE_STATS + EXTRA_STATS
    combined, all_warnings = [], []

    with sync_playwright() as p:
        if args.cdp:
            # Attach to a Chrome window you started and signed in to yourself.
            try:
                browser = p.chromium.connect_over_cdp(args.cdp)
            except PlaywrightError:
                sys.exit(f"Couldn't connect to Chrome at {args.cdp}. Start Chrome with "
                         "--remote-debugging-port=9222 first (see README).")
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.new_page()
        else:
            try:
                ctx = p.chromium.launch_persistent_context(
                    args.profile, channel="chrome", headless=False, chromium_sandbox=True)
            except Exception:  # noqa: BLE001 - Chrome not installed; use Playwright's Chromium
                ctx = p.chromium.launch_persistent_context(args.profile, headless=False, chromium_sandbox=True)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for url in urls:
            result = scrape_team(ctx, page, url, args.delay)
            if not result:
                continue
            team, slug, by_game, warnings, page = result
            totals = aggregate(by_game)
            write_csv(out / f"{slug}_batting_totals.csv", totals, cols)
            write_csv(out / f"{slug}_batting_by_game.csv", by_game, game_cols)
            print_table(team["name"], totals)
            combined += [{"team": team["name"], **r} for r in totals]
            all_warnings += [f"{team['name']}: {w}" for w in warnings]
        if args.cdp:
            page.close()  # leave your own Chrome window running
        else:
            ctx.close()

    if combined:
        write_csv(out / "all_teams_batting_totals.csv", combined, ["team"] + cols)
    print(f"\nCSV files written to {out.resolve()}")
    if all_warnings:
        print("\nWarnings:")
        for w in all_warnings:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
