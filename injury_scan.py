# -*- coding: utf-8 -*-
"""
Missing-players / injury-suspension scanner -- prototype.

Pulls injury, suspension, and doubtful-player reports for upcoming fixtures
in the top 5 European leagues + Champions League, using API-Football's free
/injuries endpoint (https://www.api-football.com). Free tier: 100 requests/
day, no card required.

This is deliberately separate from the odds scanner (scan_live_odds.py /
ev_scanner_lib.py) -- different provider, different key, different job. It
answers "who's confirmed out or doubtful for this match", which is available
days ahead of kickoff -- unlike a *confirmed starting lineup*, which nowhere
free/legit publishes more than 30-60 minutes before kickoff (checked
Highlightly, API-Football and Sportmonks -- same wall everywhere). This
script does NOT attempt to guess a starting XI. It reports player-level
injury/suspension/doubt status, which is the actual signal that moves lines
early, not a formation graphic.

SCHEMA WARNING: I built the parser against API-Football's public docs, not
a live response -- I don't have a key to test with. Run with --raw first
against one fixture before trusting the parsed report. If field names have
drifted, the raw dump shows you the real shape so parse_injury() can be
fixed to match.

Get a free key (no card, 100 requests/day):
    https://dashboard.api-football.com/register
Set it via env var API_FOOTBALL_KEY, or save it in a local file named
api_football_key.txt next to this script (same pattern as scan_live_odds.py
and its odds_api_key.txt -- both are gitignored, never commit either).

Run:
    python injury_scan.py                # full report, all 5 competitions
    python injury_scan.py --raw          # dump one raw fixture+injuries call
    python injury_scan.py --league 39    # just the Premier League (id 39)
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://v3.football.api-sports.io"
KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_football_key.txt")

# API-Football's static league IDs (stable across seasons, per their docs).
LEAGUES = {
    39: "Premier League",
    140: "La Liga",
    78: "Bundesliga",
    135: "Serie A",
    2: "Champions League",
}

FIXTURES_PER_LEAGUE = 10   # "next N" fixtures to check per competition
REQUEST_PAUSE_SEC = 0.7    # be polite to the free-tier rate limit


def get_api_key():
    env = os.environ.get("API_FOOTBALL_KEY")
    if env:
        return env.strip()
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def current_season_year():
    """API-Football seasons are keyed by the year the season starts (e.g.
    "2026" for the 2026/27 season). These leagues are in their summer close
    season through July -- the "next" fixtures endpoint still returns
    whatever's scheduled once the season year rolls over."""
    now = datetime.datetime.utcnow()
    return now.year if now.month >= 7 else now.year - 1


def api_get(path, params, api_key):
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"x-apisports-key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} on {path}: {body[:300]}")


def fetch_next_fixtures(league_id, season, api_key, n=FIXTURES_PER_LEAGUE):
    data = api_get("/fixtures", {"league": league_id, "season": season, "next": n}, api_key)
    return data.get("response", [])


def fetch_injuries_for_fixture(fixture_id, api_key):
    data = api_get("/injuries", {"fixture": fixture_id}, api_key)
    return data.get("response", [])


def parse_injury(entry):
    """Best-effort parse of one /injuries response item.

    Documented shape (unverified against a live response -- see --raw):
      entry["player"] = {"id", "name", "photo", "type", "reason"}
      entry["team"]   = {"id", "name", "logo"}
      entry["fixture"] = {"id", "date", ...}
    "type" is typically "Missing Fixture" (ruled out) or "Questionable"
    (doubtful). "reason" is free text ("Knee Injury", "Suspended",
    "Illness", "Coach Decision", etc.).
    """
    player = entry.get("player", {})
    team = entry.get("team", {})
    return {
        "player": player.get("name", "?"),
        "status": player.get("type", "?"),
        "reason": player.get("reason", "?"),
        "team": team.get("name", "?"),
    }


def run_raw_check(api_key):
    season = current_season_year()
    league_id = 39
    print(f"Fetching next fixture for league {league_id} (Premier League), season {season}...")
    fixtures = fetch_next_fixtures(league_id, season, api_key, n=1)
    if not fixtures:
        print("No upcoming fixtures returned -- season may not be scheduled yet, or season year is off.")
        return
    fx = fixtures[0]
    fixture_id = fx["fixture"]["id"]
    home = fx["teams"]["home"]["name"]
    away = fx["teams"]["away"]["name"]
    print(f"Fixture: {home} vs {away} (id {fixture_id}) on {fx['fixture']['date']}")
    print("\n--- Raw fixture object (truncated) ---")
    print(json.dumps(fx, indent=2)[:2000])

    print("\nFetching injuries for this fixture...")
    injuries = fetch_injuries_for_fixture(fixture_id, api_key)
    print(f"\n{len(injuries)} injury/suspension entries. --- Raw response (truncated) ---")
    print(json.dumps(injuries, indent=2)[:3000])
    print(
        "\nCompare the field names above against parse_injury() in this file -- "
        "if they differ, fix the parser before trusting run_full_scan()."
    )


def run_full_scan(api_key, only_league=None):
    season = current_season_year()
    leagues = {only_league: LEAGUES[only_league]} if only_league else LEAGUES
    report = []
    for league_id, league_name in leagues.items():
        print(f"\n=== {league_name} (season {season}) ===")
        try:
            fixtures = fetch_next_fixtures(league_id, season, api_key)
        except RuntimeError as e:
            print(f"  Could not fetch fixtures: {e}")
            continue
        time.sleep(REQUEST_PAUSE_SEC)
        if not fixtures:
            print("  No upcoming fixtures scheduled yet.")
            continue

        for fx in fixtures:
            fixture_id = fx["fixture"]["id"]
            date = fx["fixture"]["date"][:16].replace("T", " ")
            home = fx["teams"]["home"]["name"]
            away = fx["teams"]["away"]["name"]
            try:
                injuries = fetch_injuries_for_fixture(fixture_id, api_key)
            except RuntimeError as e:
                print(f"  {home} vs {away} ({date}): could not fetch injuries -- {e}")
                time.sleep(REQUEST_PAUSE_SEC)
                continue
            time.sleep(REQUEST_PAUSE_SEC)

            if not injuries:
                print(f"  {home} vs {away} ({date}): no reported injuries/suspensions yet")
                continue

            print(f"  {home} vs {away} ({date}):")
            for entry in injuries:
                parsed = parse_injury(entry)
                print(f"    - {parsed['player']} ({parsed['team']}) -- {parsed['status']}: {parsed['reason']}")
                report.append({"match": f"{home} vs {away}", "date": date, **parsed})

    print(f"\nTotal: {len(report)} injury/suspension/doubt entries across the scanned fixtures.")
    return report


def main():
    parser = argparse.ArgumentParser(description="Missing-players scanner prototype (API-Football)")
    parser.add_argument("--raw", action="store_true", help="Dump one raw fixture+injuries response to confirm schema")
    parser.add_argument("--league", type=int, default=None, help="Only scan this league ID (e.g. 39 for EPL)")
    args = parser.parse_args()

    api_key = get_api_key()
    if not api_key:
        print(f"No API key found. Set env var API_FOOTBALL_KEY, or save your key in:\n  {KEY_FILE}")
        print("Get a free key (no card, 100 req/day): https://dashboard.api-football.com/register")
        sys.exit(1)

    if args.league is not None and args.league not in LEAGUES:
        print(f"Unknown league id {args.league}. Known ids: {LEAGUES}")
        sys.exit(1)

    if args.raw:
        run_raw_check(api_key)
    else:
        run_full_scan(api_key, only_league=args.league)


if __name__ == "__main__":
    main()
