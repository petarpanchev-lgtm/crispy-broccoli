# -*- coding: utf-8 -*-
"""
Shared missing-players (injuries/suspensions/doubts) logic.

Pure functions only -- mirrors ev_scanner_lib.py's shape so app.py can call
this the same way it calls scan_all() for odds. Uses API-Football's free
/injuries endpoint (https://www.api-football.com) -- a separate provider,
separate key, separate free-tier budget (100 requests/day) from The Odds
API used for the odds side of this app.

This reports player-level injury/suspension/doubt status, which is
available days ahead of kickoff. It does NOT attempt to guess a starting
XI -- no free/legit source publishes a confirmed lineup more than 30-60
minutes before kickoff (checked Highlightly, API-Football and Sportmonks).

SCHEMA WARNING: parse_injury() is built from API-Football's public docs,
not a verified live response -- no key was available to test against while
building this. app.py exposes the raw JSON for the first fixture checked in
an expander so you can sanity-check the field names against what's actually
being parsed before trusting the table.
"""
import datetime

import requests

API_BASE = "https://v3.football.api-sports.io"

# API-Football's static league IDs (stable across seasons, per their docs).
LEAGUES = {
    39: "Premier League",
    140: "La Liga",
    78: "Bundesliga",
    135: "Serie A",
    2: "Champions League",
    1: "FIFA World Cup",
}

# The World Cup only happens once every 4 years -- its "season" is just the
# tournament year (2026), not something that rolls over with the European
# close season like the domestic leagues. Hardcoded rather than derived from
# current_season_year() so this doesn't silently break once the calendar
# rolls into the next European season while the World Cup is still recent.
SEASON_OVERRIDES = {
    1: 2026,  # FIFA World Cup 2026
}

DEFAULT_FIXTURES_PER_LEAGUE = 5
REQUEST_TIMEOUT = 20


def current_season_year():
    """API-Football seasons are keyed by the year the season starts (e.g.
    "2026" for the 2026/27 season); these leagues are in close season
    through July."""
    now = datetime.datetime.utcnow()
    return now.year if now.month >= 7 else now.year - 1


def season_for_league(league_id):
    return SEASON_OVERRIDES.get(league_id, current_season_year())


def api_get(path, params, api_key):
    url = f"{API_BASE}{path}"
    headers = {"x-apisports-key": api_key}
    resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_next_fixtures(league_id, season, api_key, n=DEFAULT_FIXTURES_PER_LEAGUE):
    data = api_get("/fixtures", {"league": league_id, "season": season, "next": n}, api_key)
    return data.get("response", [])


def fetch_injuries_for_fixture(fixture_id, api_key):
    data = api_get("/injuries", {"fixture": fixture_id}, api_key)
    return data.get("response", [])


def parse_injury(entry):
    """Best-effort parse of one /injuries response item -- see SCHEMA
    WARNING above. Documented shape:
      entry["player"] = {"id", "name", "photo", "type", "reason"}
      entry["team"]   = {"id", "name", "logo"}
    "type" is typically "Missing Fixture" (ruled out) or "Questionable"
    (doubtful). "reason" is free text ("Knee Injury", "Suspended", etc.).
    """
    player = entry.get("player", {})
    team = entry.get("team", {})
    return {
        "player": player.get("name", "?"),
        "status": player.get("type", "?"),
        "reason": player.get("reason", "?"),
        "team": team.get("name", "?"),
    }


def scan_injuries_all(api_key, league_ids=None, fixtures_per_league=DEFAULT_FIXTURES_PER_LEAGUE):
    """Run a full missing-players scan across league_ids.

    Returns (rows, stats, sample_raw):
      rows       -- list of dicts: league, match, date, player, status, reason, team
      stats      -- dict with fixtures_checked, leagues_with_no_fixtures, errors, requests_used
      sample_raw -- (fixture_dict, injuries_list) for the first fixture checked,
                    or None if nothing was fetched -- for schema sanity-checking.
    """
    league_ids = league_ids or list(LEAGUES.keys())
    rows = []
    stats = {
        "fixtures_checked": 0,
        "leagues_with_no_fixtures": [],
        "errors": [],
        "requests_used": 0,
    }
    sample_raw = None

    for league_id in league_ids:
        league_name = LEAGUES.get(league_id, str(league_id))
        season = season_for_league(league_id)
        try:
            fixtures = fetch_next_fixtures(league_id, season, api_key, n=fixtures_per_league)
            stats["requests_used"] += 1
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            stats["errors"].append(f"{league_name}: HTTP {code}")
            continue
        except Exception as e:
            stats["errors"].append(f"{league_name}: {e}")
            continue

        if not fixtures:
            stats["leagues_with_no_fixtures"].append(league_name)
            continue

        for fx in fixtures:
            fixture_id = fx["fixture"]["id"]
            date = fx["fixture"]["date"][:16].replace("T", " ")
            home = fx["teams"]["home"]["name"]
            away = fx["teams"]["away"]["name"]
            stats["fixtures_checked"] += 1
            try:
                injuries = fetch_injuries_for_fixture(fixture_id, api_key)
                stats["requests_used"] += 1
            except requests.exceptions.HTTPError as e:
                code = e.response.status_code if e.response is not None else "?"
                stats["errors"].append(f"{home} vs {away}: HTTP {code}")
                continue
            except Exception as e:
                stats["errors"].append(f"{home} vs {away}: {e}")
                continue

            if sample_raw is None:
                sample_raw = (fx, injuries)

            for entry in injuries:
                parsed = parse_injury(entry)
                rows.append({
                    "league": league_name,
                    "match": f"{home} vs {away}",
                    "date": date,
                    **parsed,
                })

    return rows, stats, sample_raw
