# -*- coding: utf-8 -*-
"""
+EV Sports Odds Scanner -- Streamlit app.

Live version of the local HTML prototype: same no-vig / two-reference-book
math (ev_scanner_lib.py), same three markets (1X2, Over/Under 2.5, Both
Teams to Score), same calculator and bet log -- but running as a proper web
app you can deploy for free on Streamlit Community Cloud and share a link
to, instead of sending people a local file.

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

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
secret_key = ""
try:
    secret_key = st.secrets.get("ODDS_API_KEY", "")
except Exception:
    secret_key = ""

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
        "(efbet, Winbet) -- it compares pan-EU books instead. BTTS coverage "
        "is also patchier than 1X2/totals."
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
# Market tabs + calculator + bet log
# ---------------------------------------------------------------------------
tab_1x2, tab_ou, tab_btts, tab_calc, tab_log = st.tabs(
    ["1X2", "Over/Under 2.5", "Both teams to score", "Try your own odds", "Bet log"]
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
        color = "background-color: #1c3b2c" if row["Value bet"] else ""
        return [color] * len(row)

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
    render_market_tab("BTTS", "Both teams to score")

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
