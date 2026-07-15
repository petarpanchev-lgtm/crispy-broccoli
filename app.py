# -*- coding: utf-8 -*-
"""
+EV Sports Odds Scanner -- Streamlit app.

Live version of the local HTML prototype: same no-vig / two-reference-book
math (ev_scanner_lib.py), same three markets (1X2, Over/Under 2.5, Both
Teams to Score), same calculator and bet log -- but running as a proper web
app you can deploy for free on Streamlit Community Cloud and share a link
to, instead of sending people a local file.

Also includes a "Missing players" tab (injuries_lib.py) -- injury,
suspension, and doubt reports for upcoming fixtures via API-Football's free
tier, a separate provider/key from the odds side of this app.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

The API key is read from Streamlit secrets (.streamlit/secrets.toml locally,
or the app's Secrets panel on Streamlit Cloud) if present, otherwise you can
paste it into the sidebar for the session. See README.md for full setup.
"""
import datetime

import pandas as pd
import streamlit as st

from ev_scanner_lib import (
    EV_THRESHOLD_PCT,
    ev_pct,
    kelly_stake,
    no_vig_probs,
    scan_all,
)
from injuries_lib import (
    DEFAULT_FIXTURES_PER_LEAGUE,
    LEAGUES as INJURY_LEAGUES,
    scan_injuries_all,
)

st.set_page_config(page_title="+EV Sports Odds Scanner", layout="wide")

st.title("+EV Sports Odds Scanner")
st.caption(
    "Finds mispriced odds by comparing bookmaker prices against a no-vig fair line, "
    "cross-checked against two reference books (Pinnacle and Marathonbet) so a stale "
    "single line can't flag a false value bet on its own."
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "rows" not in st.session_state:
    st.session_state.rows = []
if "scan_stats" not in st.session_state:
    st.session_state.scan_stats = None
if "last_scan_time" not in st.session_state:
    st.session_state.last_scan_time = None
if "bet_log" not in st.session_state:
    st.session_state.bet_log = pd.DataFrame(
        columns=["date", "match", "market", "outcome", "book", "odds", "stake", "result"]
    )
if "injury_rows" not in st.session_state:
    st.session_state.injury_rows = []
if "injury_stats" not in st.session_state:
    st.session_state.injury_stats = None
if "injury_sample_raw" not in st.session_state:
    st.session_state.injury_sample_raw = None
if "last_injury_scan_time" not in st.session_state:
    st.session_state.last_injury_scan_time = None

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
secret_key = ""
try:
    secret_key = st.secrets.get("ODDS_API_KEY", "")
except Exception:
    secret_key = ""

secret_football_key = ""
try:
    secret_football_key = st.secrets.get("API_FOOTBALL_KEY", "")
except Exception:
    secret_football_key = ""

with st.sidebar:
    st.header("Settings")
    api_key_input = st.text_input(
        "Odds API key",
        value=secret_key,
        type="password",
        help="Free key from the-odds-api.com (500 credits/month). "
             "Set as a Secret on Streamlit Cloud to avoid re-entering it, "
             "or paste it here for this session only.",
    )
    bankroll = st.number_input("Bankroll (EUR)", value=1000, step=50, min_value=0)
    ev_threshold = st.slider("Flag threshold (edge %)", 0.5, 10.0, EV_THRESHOLD_PCT, 0.5)
    run_scan = st.button("Run live scan", type="primary", use_container_width=True)
    if st.session_state.last_scan_time:
        st.caption(f"Last scan: {st.session_state.last_scan_time.strftime('%Y-%m-%d %H:%M')}")
    st.divider()
    st.caption(
        "Known gap: this API doesn't cover Bulgarian-specific bookmakers "
        "(efbet, Winbet) -- it compares pan-EU books instead. Both Teams to "
        "Score is not scanned at all -- it needs a different, more expensive "
        "API endpoint (see the Both teams to score tab)."
    )

    st.divider()
    st.subheader("Missing players (beta)")
    api_football_key_input = st.text_input(
        "API-Football key",
        value=secret_football_key,
        type="password",
        help="Separate free key from dashboard.api-football.com (100 requests/day, "
             "no card). Different provider from the odds key above.",
    )
    fixtures_per_league = st.slider(
        "Fixtures to check per league", 1, 10, DEFAULT_FIXTURES_PER_LEAGUE, 1,
        help="Each fixture costs 1 request for the fixture list + 1 for its injury "
             "report. Keep this low to stay inside the 100/day free budget.",
    )
    run_injury_scan = st.button("Run missing-players scan", use_container_width=True)
    if st.session_state.last_injury_scan_time:
        st.caption(
            f"Last injury scan: {st.session_state.last_injury_scan_time.strftime('%Y-%m-%d %H:%M')}"
        )
    st.caption(
        "Reports injuries/suspensions/doubts, available days ahead of kickoff. "
        "This is NOT a predicted starting XI -- no free source publishes a confirmed "
        "lineup more than 30-60 minutes before kickoff. Schema is unverified against "
        "a live response -- check the raw JSON expander on the tab before trusting it."
    )

if run_scan:
    if not api_key_input:
        st.error("Enter an API key first (sign up free at the-odds-api.com).")
    else:
        with st.spinner("Scanning live odds across 5 leagues and 3 markets..."):
            rows, stats = scan_all(api_key_input)
        st.session_state.rows = rows
        st.session_state.scan_stats = stats
        st.session_state.last_scan_time = datetime.datetime.now()

if run_injury_scan:
    if not api_football_key_input:
        st.error("Enter an API-Football key first (sign up free at dashboard.api-football.com).")
    else:
        with st.spinner("Checking upcoming fixtures for injuries/suspensions/doubts..."):
            injury_rows, injury_stats, sample_raw = scan_injuries_all(
                api_football_key_input, fixtures_per_league=fixtures_per_league
            )
        st.session_state.injury_rows = injury_rows
        st.session_state.injury_stats = injury_stats
        st.session_state.injury_sample_raw = sample_raw
        st.session_state.last_injury_scan_time = datetime.datetime.now()

# ---------------------------------------------------------------------------
# Scan summary
# ---------------------------------------------------------------------------
stats = st.session_state.scan_stats
if stats:
    flagged_n = len([r for r in st.session_state.rows if r["ev"] >= ev_threshold])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Events scanned", stats["events_seen"])
    c2.metric("Rows checked", len(st.session_state.rows))
    c3.metric("Value bets flagged", flagged_n)
    c4.metric("API credits left", stats.get("credits_remaining") or "—")
    if stats["errors"]:
        st.warning("Some sports failed to fetch: " + "; ".join(stats["errors"]))
elif not st.session_state.rows:
    st.info("Enter your API key in the sidebar and click **Run live scan** to pull real odds.")

# ---------------------------------------------------------------------------
# Market tabs + calculator + bet log + missing players
# ---------------------------------------------------------------------------
tab_1x2, tab_ou, tab_btts, tab_calc, tab_log, tab_injuries = st.tabs(
    ["1X2", "Over/Under 2.5", "Both teams to score", "Try your own odds", "Bet log", "Missing players"]
)


def render_market_tab(market_key, market_label):
    rows = [r for r in st.session_state.rows if r["market"] == market_key]
    if not rows:
        st.info("No scan data yet for this market -- run a live scan from the sidebar.")
        return

    df = pd.DataFrame(rows).sort_values("ev", ascending=False).reset_index(drop=True)
    df["Value bet"] = df["ev"] >= ev_threshold
    display_df = df[["match", "outcome", "book", "odds", "fairOdds", "ev", "Value bet"]].rename(
        columns={"match": "Match", "outcome": "Outcome", "book": "Book", "odds": "Odds",
                 "fairOdds": "Fair odds", "ev": "Edge %"}
    )

    def highlight_value(row):
        style = "background-color: #c6f0d8; color: #0a3d24; font-weight: 600" if row["Value bet"] else ""
        return [style] * len(row)

    st.dataframe(
        display_df.style.format({"Odds": "{:.2f}", "Fair odds": "{:.2f}", "Edge %": "{:+.1f}%"}).apply(
            highlight_value, axis=1
        ),
        use_container_width=True,
        hide_index=True,
    )

    flagged = df[df["Value bet"]]
    if len(flagged):
        st.write(f"**{len(flagged)} value bet(s) flagged** -- log one below:")
        options = [
            f"{r['match']} - {r['outcome']} @ {r['book']} ({r['odds']:.2f}, {r['ev']:+.1f}%)"
            for _, r in flagged.iterrows()
        ]
        sel = st.selectbox("Pick a bet", options, key=f"sel_{market_key}")
        if st.button("Add to bet log", key=f"logbtn_{market_key}"):
            row = flagged.iloc[options.index(sel)]
            fair_prob = 1.0 / row["fairOdds"]
            stake = round(kelly_stake(row["odds"], fair_prob, bankroll, 0.25)) or 10
            new_row = {
                "date": datetime.date.today().isoformat(),
                "match": row["match"],
                "market": market_key,
                "outcome": row["outcome"],
                "book": row["book"],
                "odds": row["odds"],
                "stake": stake,
                "result": "Pending",
            }
            st.session_state.bet_log = pd.concat(
                [st.session_state.bet_log, pd.DataFrame([new_row])], ignore_index=True
            )
            st.success(f"Logged: {row['match']} - {row['outcome']} @ {row['book']}")


with tab_1x2:
    render_market_tab("1X2", "1X2")
with tab_ou:
    render_market_tab("OU25", "Over/Under 2.5")
with tab_btts:
    st.warning(
        "Both Teams to Score isn't scanned by this app. The Odds API classes BTTS as an "
        "\"Additional Market\" that only works through a separate per-event endpoint "
        "(one API call per match, not one call per league) -- adding it to the same bulk "
        "request as 1X2 and Over/Under actually broke the whole scan (HTTP 422) rather than "
        "just coming back empty. Supporting it properly would multiply the credit cost a lot, "
        "so it's left out for now rather than pretending it works. The calculator tab still "
        "handles two-way markets like BTTS if you want to check one manually."
    )

with tab_calc:
    st.subheader("Try your own odds")
    st.caption("Real math on whatever numbers you enter -- doesn't depend on a live scan.")
    market_mode = st.radio("Market", ["1X2", "Two-way (O/U, BTTS, etc.)"], horizontal=True)
    c1, c2, c3 = st.columns(3)
    if market_mode == "1X2":
        ref_h = c1.number_input("Reference: Home odds", value=2.05, step=0.01, format="%.2f")
        ref_d = c2.number_input("Reference: Draw odds", value=3.60, step=0.01, format="%.2f")
        ref_a = c3.number_input("Reference: Away odds", value=3.50, step=0.01, format="%.2f")
        ref_odds = [ref_h, ref_d, ref_a]
        outcome = st.selectbox("Outcome to check", ["Home", "Draw", "Away"])
        idx = {"Home": 0, "Draw": 1, "Away": 2}[outcome]
        side_label = outcome
    else:
        ref_a_side = c1.number_input("Reference: Side A odds", value=1.92, step=0.01, format="%.2f")
        ref_b_side = c2.number_input("Reference: Side B odds", value=1.98, step=0.01, format="%.2f")
        ref_odds = [ref_a_side, ref_b_side]
        outcome = st.selectbox("Outcome to check", ["Side A", "Side B"])
        idx = {"Side A": 0, "Side B": 1}[outcome]
        side_label = outcome

    book_odds = st.number_input("Your book's odds on that outcome", value=2.20, step=0.01, format="%.2f")

    if all(o > 0 for o in ref_odds) and book_odds > 0:
        fair = no_vig_probs(ref_odds)
        fair_prob = fair[idx]
        ev = ev_pct(book_odds, fair_prob)
        stake = kelly_stake(book_odds, fair_prob, bankroll, 0.25)

        m1, m2, m3 = st.columns(3)
        m1.metric("Fair probability", f"{fair_prob * 100:.1f}%")
        m2.metric("Edge (EV)", f"{ev:+.1f}%")
        m3.metric("Suggested stake (¼ Kelly)", f"€{stake:.0f}")

        if ev > ev_threshold:
            st.success(
                f"This book pays {book_odds:.2f} on {side_label}, vs a fair price of "
                f"{1 / fair_prob:.2f}. That's a {ev:.1f}% edge -- above your "
                f"{ev_threshold}% flag threshold."
            )
        elif ev > 0:
            st.info(f"Small edge ({ev:.1f}%), below your {ev_threshold}% flag threshold.")
        else:
            st.error(f"No edge -- this book pays less than fair value ({ev:.1f}%).")

with tab_log:
    st.subheader("Bet log")
    st.caption(
        "Editable -- update Result as bets settle. Resets if the app restarts or redeploys; "
        "download a CSV below to keep a permanent record."
    )
    edited = st.data_editor(
        st.session_state.bet_log,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "result": st.column_config.SelectboxColumn("result", options=["Pending", "Win", "Loss", "Push"]),
            "stake": st.column_config.NumberColumn("stake", min_value=0),
        },
        key="bet_log_editor",
    )
    st.session_state.bet_log = edited

    if len(edited):

        def pnl(row):
            if row["result"] == "Win":
                return row["stake"] * (row["odds"] - 1)
            if row["result"] == "Loss":
                return -row["stake"]
            return 0.0

        computed = edited.copy()
        computed["pnl"] = computed.apply(pnl, axis=1)
        settled = computed[computed["result"].isin(["Win", "Loss", "Push"])]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Bets logged", len(computed))
        c2.metric("Total staked", f"€{computed['stake'].sum():.0f}")
        c3.metric("Settled P&L", f"€{settled['pnl'].sum():+.0f}")
        roi = (settled["pnl"].sum() / settled["stake"].sum() * 100) if settled["stake"].sum() else 0
        c4.metric("ROI (settled)", f"{roi:.1f}%" if len(settled) else "—")

        st.download_button(
            "Download bet log as CSV",
            computed.to_csv(index=False),
            file_name="ev_scanner_bet_log.csv",
            mime="text/csv",
        )
    else:
        st.caption("No bets logged yet -- flag one from a market tab above.")

with tab_injuries:
    st.subheader("Missing players")
    st.caption(
        "Injuries, suspensions, and doubts for upcoming fixtures in the 5 leagues above, "
        "via API-Football's free /injuries endpoint -- separate provider and key from the "
        "odds side of this app. This is who's reported out or doubtful, days ahead of "
        "kickoff, not a predicted starting XI (nobody publishes that free and reliably -- "
        "confirmed lineups land 30-60 minutes before kickoff everywhere, paid or free)."
    )

    injury_stats = st.session_state.injury_stats
    if injury_stats:
        c1, c2, c3 = st.columns(3)
        c1.metric("Fixtures checked", injury_stats["fixtures_checked"])
        c2.metric("Entries found", len(st.session_state.injury_rows))
        c3.metric("API requests used", injury_stats["requests_used"])
        if injury_stats["leagues_with_no_fixtures"]:
            st.caption(
                "No fixtures scheduled yet for: " + ", ".join(injury_stats["leagues_with_no_fixtures"])
            )
        if injury_stats["errors"]:
            st.warning("Some lookups failed: " + "; ".join(injury_stats["errors"]))
    elif not st.session_state.injury_rows:
        st.info(
            "Enter your API-Football key in the sidebar and click **Run missing-players scan**."
        )

    if st.session_state.injury_sample_raw:
        sample_fx, sample_injuries = st.session_state.injury_sample_raw
        with st.expander("Raw JSON for the first fixture checked (schema sanity-check)"):
            st.caption(
                "Compare these field names against injuries_lib.py's parse_injury() -- "
                "the parser was built from API-Football's docs, not a verified live "
                "response. If names differ here, the table below is likely wrong."
            )
            st.json({"fixture": sample_fx, "injuries": sample_injuries})

    if st.session_state.injury_rows:
        idf = pd.DataFrame(st.session_state.injury_rows)
        idf = idf.sort_values(["league", "date", "match"]).reset_index(drop=True)
        display_idf = idf[["league", "match", "date", "team", "player", "status", "reason"]].rename(
            columns={
                "league": "League", "match": "Match", "date": "Kickoff",
                "team": "Team", "player": "Player", "status": "Status", "reason": "Reason",
            }
        )
        st.dataframe(display_idf, use_container_width=True, hide_index=True)
    elif not injury_stats:
        pass
    else:
        st.caption("No reported injuries/suspensions/doubts for the fixtures checked.")
