# +EV Sports Odds Scanner

Finds mispriced soccer odds by comparing bookmaker prices against a no-vig
fair line, cross-checked against two independent reference books (Pinnacle
and Marathonbet) so a stale single line can't flag a false value bet on its
own. Covers three markets: 1X2 (match winner), Over/Under 2.5 goals, and
Both Teams to Score.

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

## Run it locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml and paste in your real API key
streamlit run app.py
```

Get a free API key at https://the-odds-api.com (no card required, 500
credits/month). A scan across 5 leagues x 3 markets costs about 15 credits,
so daily runs stay well inside the free tier.

If you'd rather not use secrets.toml, you can also just paste the key into
the sidebar each time you open the app -- it's kept only for that session.

## Put it on GitHub

This folder isn't a git repo yet -- I couldn't run `git init` from my side
(the mounted folder doesn't support git's lock files), so this needs to
happen from a terminal on your own machine, inside this folder:

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

**Important:** `.streamlit/secrets.toml` and `odds_api_key.txt` are in
`.gitignore` on purpose -- don't remove that, or your API key would end up
public on GitHub.

## Deploy for free on Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with your GitHub account.
2. Click **New app**, pick the repo you just pushed, branch `main`, and set
   the main file path to `app.py`.
3. Before or after deploying, open the app's **Settings -> Secrets** and add:
   ```
   ODDS_API_KEY = "your-real-key-here"
   ```
   This keeps the key out of the public repo while still letting the
   deployed app read it via `st.secrets`.
4. Deploy. You'll get a public URL (e.g.
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
