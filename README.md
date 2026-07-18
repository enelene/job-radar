# Innsbruck Job & Volunteer Radar

Runs once a day for free on GitHub Actions. Searches for:

- **MLOps** roles (junior / mid-level / internship) in or near Innsbruck, or
  anywhere that explicitly mentions relocation/visa support to Austria.
- **DevOps** roles, same criteria (for a second person relocating together).
- **Volunteer opportunities** in Innsbruck (Freiwilligenarbeit).

New results are sent to a Telegram chat via a bot. Only postings not seen in a
previous run are sent (tracked in `seen_jobs.json`, committed back by the
workflow each run).

Everything runs on free tiers: GitHub Actions (public repo = unlimited free
minutes), the Arbeitnow job API (no key, no cost), and Google's Programmable
Search Engine (100 free queries/day, which this script comfortably stays
under: ~14 queries/day).

## One-time setup (~15 minutes)

### 1. Create a Telegram bot

1. In Telegram, open a chat with **@BotFather**.
2. Send `/newbot`, give it a name and a username (must end in `bot`).
3. BotFather replies with an **HTTP API token** — copy it. This is
   `TELEGRAM_BOT_TOKEN`.
4. Open a chat with your new bot and send it any message (e.g. "hi") so it's
   allowed to message you back.
5. Get your chat ID: visit
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser
   (replace `<YOUR_TOKEN>`), send another message to the bot first if the
   response is empty, then reload. Look for `"chat":{"id":123456789,...}` —
   that number is `TELEGRAM_CHAT_ID`.

### 2. Create a free Google Custom Search API key + engine

This powers the karriere.at / StepStone / EURES / volunteer-site searches
(Arbeitnow works without this, so the radar still functions if you skip this
step, just with less coverage).

1. Go to https://programmablesearchengine.google.com/ and create a new search
   engine. Under "Sites to search" you can leave it set to "Search the entire
   web" (the script restricts results per-site itself via `site:` queries).
2. Copy the **Search engine ID** — that's `GOOGLE_CSE_ID`.
3. Go to https://console.cloud.google.com/apis/credentials, create a project
   if you don't have one, enable the **Custom Search API**, then create an
   **API key**. That's `GOOGLE_CSE_API_KEY`.
4. Free tier is 100 queries/day; this job uses roughly 8 sites x 2 queries for
   jobs + 4 sites for volunteering = ~20 queries/day, well within budget.

### 3. Push this folder to a GitHub repo

Ask your assistant (or do it yourself) to `git init`, commit, create a GitHub
repo, and push — a public repo keeps Actions minutes unlimited and free.

### 4. Add the four secrets to the repo

In the GitHub repo: **Settings -> Secrets and variables -> Actions -> New
repository secret**. Add:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GOOGLE_CSE_API_KEY` (optional but recommended)
- `GOOGLE_CSE_ID` (optional but recommended)

### 5. Test it

Go to the **Actions** tab -> "Daily Innsbruck job radar" -> **Run workflow**
to trigger it manually instead of waiting for the 06:00 UTC schedule.

## Tuning

Edit the keyword lists near the top of `job_radar.py`:

- `LOCATION_KEYWORDS` — widen/narrow the geographic net (currently Innsbruck,
  Tyrol, Austria).
- `LEVEL_KEYWORDS` — seniority terms to match.
- `RELOCATION_KEYWORDS` — phrases indicating relocation/visa support.
- `JOB_SITES` / `VOLUNTEER_SITES` — which sites the Google CSE queries target.

## Known limitations

- Innsbruck-specific MLOps openings are rare in absolute terms — this casts a
  wider net (all of Austria + relocation-friendly remote roles) rather than
  Innsbruck city limits only, since a strict filter would return almost
  nothing most days.
- "Middle" seniority isn't a standard Western job-ad term — the script
  matches "mid-level"/"mid level"/"middle" but many relevant postings won't
  label seniority explicitly at all, so `level_match: false` doesn't mean
  "not relevant," just "unlabeled."
- LinkedIn is intentionally not scraped (violates their Terms of Service).
