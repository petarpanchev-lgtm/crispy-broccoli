# +EV Sports Odds Scanner

Finds mispriced soccer odds by comparing bookmaker prices against a no-vig
fair line, cross-checked against two independent reference books (Pinnacle
and Marathonbet) so a stale single line can't flag a false value bet on its
own. Covers three markets: 1X2 (match winner), Over/Under 2.5 goals, and
Both Teams to Score.

Also includes a **Missing players** tab -- injuries, suspensions, and doubts
for upcoming fixtures in the same 5 competitions, via a separate free API
(API-Football). This is player-level availability, days ahead of kickoff --
not a predicted starting XI. No free or paid source reliably publishes a
confirmed lineup more than 30-60 minutes before kickoff, and Flashscore's
"predicted lineups" can't legally be scraped (their terms of use prohibit
it, and there's no official API), so this tab reports the actual signal
that's available early: who's out, doubtful, or suspended.

This is the Streamlit version of the local HTML prototype -- same math
(`ev_scanner_lib.py`), but runnable as a shareable web app instead of a file
you send people.

**Known gaps, on purpose, not hidden:**
- The Odds API doesn't cover Bulgarian-specific bookmakers (efbet, Winbet).
  It covers Pinnacle plus several pan-EU books. Whether edges found against
  those pan-EU books are actually accessible/relevant to a Bulgarian bettor
  is still an open assumption.
- Both Teams to Score has patchier coverage than 1X2/totals on this API --
  don't be surprised by zero BTTS rows on some scans.
- The Missing players tab's parser was built from API-Football's public
  docs, not a verified live response (no key was available while building
  it). Check the "Raw JSON" expander on that tab against `injuries_lib.py`'s
  `parse_injury()` before trusting the table -- if field names have
  drifted, fix the parser to match what you actually see there.

## Run it locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml and paste in your real API key(s)
streamlit run app.py
```

Get a free API key at https://the-odds-api.com (no card required, 500
credits/month). A scan across 5 leagues x 2 markets costs about 10 credits,
so daily runs stay well inside the free tier.

For the Missing players tab, get a second, separate free key at
https://dashboard.api-football.com/register (no card, 100 requests/day) and
add it to `secrets.toml` as `API_FOOTBALL_KEY` the same way. Each fixture
checked costs 2 requests (1 for the fixture list, 1 for its injury report),
so keep the "fixtures per league" slider low if you're running this often.

If you'd rather not use secrets.toml, you can also just paste either key into
the sidebar each time you open the app -- it's kept only for that session.

## Put it on GitHub

If this is your first time setting this repo up: this folder isn't a git
repo yet -- I couldn't run `git init` from my side (the mounted folder
doesn't support git's lock files), so this needs to happen from a terminal
on your own machine, inside this folder:

1. If you see a `.git` folder here already, delete it first (it's a leftover
   from a failed attempt on my end, not a real repo) -- `rm -rf .git` on
   Mac/Linux, or just delete it in File Explorer on Windows.
2. Initialize and commit:
   ```bash
   cd "path/to/Online Business/ev-scanner-app"
   git init
   git add -A
   git commit -m "Initial commit: +EV Sports Odds Scanner"
   ```
3. Go to https://github.com/new and create a new **empty** repository (no
   README, no .gitignore, no license -- this folder already has those).
   Name it whatever you like, e.g. `ev-scanner-app`.
4. GitHub will show you a remote URL, something like
   `https://github.com/<your-username>/ev-scanner-app.git`. Run:
   ```bash
   git remote add origin https://github.com/<your-username>/ev-scanner-app.git
   git branch -M main
   git push -u origin main
   ```
   You'll be prompted to sign in to GitHub the first time (browser popup or
   a personal access token, depending on how git is configured on your
   machine). This step has to be you -- I can't authenticate as you on
   GitHub.

If you already have this repo pushed to GitHub from before (this folder
already has a `.git` here), you can skip straight to committing and pushing
the new files:
```bash
cd "path/to/Online Business/ev-scanner-app"
git add -A
git commit -m "Add Missing players tab (injuries/suspensions/doubts)"
git push
```

**Important:** `.streamlit/secrets.toml`, `odds_api_key.txt`, and
`api_football_key.txt` are all in `.gitignore` on purpose -- don't remove
that, or your API keys would end up public on GitHub.

## Deploy for free on Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with your GitHub account.
2. Click **New app**, pick the repo you just pushed, branch `main`, and set
   the main file path to `app.py`.
3. Before or after deploying, open the app's **Settings -> Secrets** and add:
   ```
   ODDS_API_KEY = "your-real-odds-api-key-here"
   API_FOOTBALL_KEY = "your-real-api-football-key-here"
   ```
   This keeps both keys out of the public repo while still letting the
   deployed app read them via `st.secrets`. The second line is only needed
   if you want the Missing players tab to work without re-entering a key
   each visit.
4. Deploy (or, if already deployed, it'll pick up the push and redeploy on
   its own within a minute or two). You'll get a public URL (e.g.
   `https://<something>.streamlit.app`) you can share with beta testers
   instead of sending a file.

Free tier apps on Streamlit Community Cloud sleep after inactivity and wake
up on the next visit (a few seconds' delay) -- fine for a prototype/beta
tool, worth knowing if you later want it always-instant.

## Notes on the bet log

The in-app bet log lives in Streamlit's session state, which resets if the
app restarts, redeploys, or you close the tab and lose the session. Use the
**Download bet log as CSV** button on the Bet log tab to keep a permanent
record outside the app. If this matters a lot once you're tracking real
bets, the natural next step is wiring in a small persistent store (a
Google Sheet, SQLite file, or similar) -- worth a separate pass once you
know you want it.
