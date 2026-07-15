# -*- coding: utf-8 -*-
"""
Shared scanning logic for the +EV Sports Odds Scanner.

Pure functions only -- no file I/O, no printing, no Streamlit imports. This
keeps the math independently testable and reusable from both the Streamlit
app (app.py) and the original standalone script.

Same approach as the local prototype: pulls soccer odds from The Odds API
across three markets (1X2, Over/Under 2.5 goals, Both Teams to Score), and
cross-checks every price against TWO independent reference books (Pinnacle
and Marathonbet) before flagging a value bet -- a stale or thin line on a
single reference book won't pass on its own. See app.py / README.md for the
known coverage gaps (no Bulgarian-specific bookmakers, patchier BTTS
coverage).
"""
import requests

API_BASE = "https://api.the-odds-api.com/v4"
REGION = "eu"
MARKETS_PARAM = "h2h,totals,btts"
REFERENCE_BOOKS = ["pinnacle", "marathonbet"]
EV_THRESHOLD_PCT = 2.0
KELLY_FRACTION_DEFAULT = 0.25
TOTALS_POINT = 2.5

SPORT_KEYS = [
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_uefa_champs_league",
]


def fetch_odds(sport_key, api_key, region=REGION, markets=MARKETS_PARAM, timeout=20):
    url = f"{API_BASE}/sports/{sport_key}/odds/"
    params = {"apiKey": api_key, "regions": region, "markets": markets, "oddsFormat": "decimal"}
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    remaining = resp.headers.get("x-requests-remaining")
    used = resp.headers.get("x-requests-used")
    return resp.json(), remaining, used


def no_vig_probs(odds):
    implied = [1.0 / o for o in odds]
    s = sum(implied)
    return [p / s for p in implied]


def ev_pct(book_odds, fair_prob):
    return (book_odds * fair_prob - 1.0) * 100.0


def kelly_stake(book_odds, fair_prob, bankroll, fraction=KELLY_FRACTION_DEFAULT):
    b = book_odds - 1.0
    q = 1.0 - fair_prob
    f_star = (b * fair_prob - q) / b if b > 0 else 0.0
    return max(0.0, f_star) * fraction * bankroll


def h2h_outcomes(market, home, away):
    if len(market["outcomes"]) != 3:
        return None
    m = {}
    for o in market["outcomes"]:
        if o["name"] == home:
            m["H"] = o["price"]
        elif o["name"] == away:
            m["A"] = o["price"]
        else:
            m["D"] = o["price"]
    if not all(k in m for k in ("H", "D", "A")):
        return None
    return m


def totals_outcomes(market, home=None, away=None):
    m = {}
    for o in market["outcomes"]:
        if o.get("point") != TOTALS_POINT:
            continue
        if o["name"] == "Over":
            m["Over"] = o["price"]
        elif o["name"] == "Under":
            m["Under"] = o["price"]
    if "Over" not in m or "Under" not in m:
        return None
    return m


def btts_outcomes(market, home=None, away=None):
    m = {}
    for o in market["outcomes"]:
        if o["name"] == "Yes":
            m["Yes"] = o["price"]
        elif o["name"] == "No":
            m["No"] = o["price"]
    if "Yes" not in m or "No" not in m:
        return None
    return m


MARKET_DEFS = [
    {"api_key": "h2h", "js_market": "1X2", "labels": ["H", "D", "A"],
     "display": {"H": "Home", "D": "Draw", "A": "Away"}, "extractor": h2h_outcomes},
    {"api_key": "totals", "js_market": "OU25", "labels": ["Over", "Under"],
     "display": {"Over": "Over 2.5", "Under": "Under 2.5"}, "extractor": totals_outcomes},
    {"api_key": "btts", "js_market": "BTTS", "labels": ["Yes", "No"],
     "display": {"Yes": "Yes", "No": "No"}, "extractor": btts_outcomes},
]


def get_market(book, api_key):
    return next((m for m in book.get("markets", []) if m["key"] == api_key), None)


def process_market(books, market_def, home, away, all_rows, reference_books=REFERENCE_BOOKS):
    api_key = market_def["api_key"]
    fair_by_ref = {}
    for rb in reference_books:
        book = books.get(rb)
        if not book:
            return False
        mk = get_market(book, api_key)
        if not mk:
            return False
        outcomes = market_def["extractor"](mk, home, away)
        if not outcomes:
            return False
        probs = no_vig_probs([outcomes[l] for l in market_def["labels"]])
        fair_by_ref[rb] = dict(zip(market_def["labels"], probs))

    match_label = f"{home} vs {away}"
    found_any = False
    for book_key, book in books.items():
        if book_key in reference_books:
            continue
        mk = get_market(book, api_key)
        if not mk:
            continue
        outcomes = market_def["extractor"](mk, home, away)
        if not outcomes:
            continue
        for label in market_def["labels"]:
            if label not in outcomes:
                continue
            found_any = True
            evs = {rb: ev_pct(outcomes[label], fair_by_ref[rb][label]) for rb in reference_books}
            conservative_ev = min(evs.values())
            avg_fair_prob = sum(fair_by_ref[rb][label] for rb in reference_books) / len(reference_books)
            all_rows.append({
                "market": market_def["js_market"],
                "match": match_label,
                "outcome": market_def["display"][label],
                "book": book_key,
                "odds": outcomes[label],
                "fairOdds": 1.0 / avg_fair_prob,
                "ev": conservative_ev,
            })
    return found_any


def scan_all(api_key, sport_keys=None, reference_books=None, region=REGION):
    """Run a full scan across sport_keys and return (all_rows, stats)."""
    sport_keys = sport_keys or SPORT_KEYS
    reference_books = reference_books or REFERENCE_BOOKS
    all_rows = []
    stats = {
        "events_seen": 0,
        "events_no_usable_market": 0,
        "credits_remaining": None,
        "credits_used": None,
        "errors": [],
    }

    for sport_key in sport_keys:
        try:
            events, remaining, used = fetch_odds(sport_key, api_key, region=region)
        except requests.exceptions.HTTPError as e:
            stats["errors"].append(f"{sport_key}: HTTP {e.response.status_code if e.response is not None else '?'}")
            continue
        except Exception as e:
            stats["errors"].append(f"{sport_key}: {e}")
            continue

        if remaining is not None:
            stats["credits_remaining"] = remaining
            stats["credits_used"] = used

        for ev in events:
            stats["events_seen"] += 1
            home, away = ev.get("home_team"), ev.get("away_team")
            books = {b["key"]: b for b in ev.get("bookmakers", [])}
            any_market_ok = False
            for market_def in MARKET_DEFS:
                ok = process_market(books, market_def, home, away, all_rows, reference_books)
                any_market_ok = any_market_ok or ok
            if not any_market_ok:
                stats["events_no_usable_market"] += 1

    all_rows.sort(key=lambda r: r["ev"], reverse=True)
    return all_rows, stats
