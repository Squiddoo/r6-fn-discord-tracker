# Discord stats tracker

Posts **Rainbow Six Siege** and **Fortnite** stat changes to a Discord webhook every **15 minutes**. Hosted entirely on GitHub Actions — no VPS, no always-on PC.

This repo is a template. Fork it, add your own secrets, run the workflow once, then leave it.

| | |
|---|---|
| Schedule | every 15 minutes (external ping; GitHub cron is only a fallback) |
| Players | 3 Siege + 3 Fortnite |
| Discord | one embed per player who actually changed; **no pings** |
| Privacy | usernames and keys stay in GitHub Secrets; `stats.json` is anonymous |

---

## What's in this repo

| Path | What it is |
|---|---|
| [`.github/workflows/workflow.yml`](.github/workflows/workflow.yml) | The 15-minute GitHub Action |
| [`.env.example`](.env.example) | Names of every secret you must fill in |
| [`stats.json`](stats.json) | Last known stats (anonymous keys only). The Action overwrites this file. |
| [`tracker/`](tracker/) | Python bot |
| [`requirements.txt`](requirements.txt) | Python dependencies |

Do **not** commit a `.env` file. Copy `.env.example` locally if you want to test on your machine.

---

## Fork & run (GitHub)

### 1. Fork or use this repo

Enable Actions on the repo (**Settings → Actions → Allow all actions**).

### 2. Create a Discord webhook

Server settings → Integrations → Webhooks → New webhook. Copy the URL.

### 3. Get API keys

| Key | Where |
|---|---|
| `FORTNITE_API_KEY` | [dash.fortnite-api.com](https://dash.fortnite-api.com/) (log in with Discord) |
| `ARENYZE_API_KEY` | [r6.arenyze.com](https://r6.arenyze.com/api-docs) — Siege fallback (recommended) |
| `UBISOFT_EMAIL` / `UBISOFT_PASSWORD` | Optional. A **throwaway** Ubisoft account for [siegeapi](https://github.com/CNDRD/siegeapi). You need **Arenyze or Ubisoft**, not both. |

Fortnite career stats must be **public** on the Epic account.

### 4. Add GitHub Secrets

**Settings → Secrets and variables → Actions → New repository secret**

Add every name from [`.env.example`](.env.example). The important ones:

| Secret | Notes |
|---|---|
| `DISCORD_WEBHOOK_URL` | Your webhook |
| `FORTNITE_API_KEY` | Required |
| `ARENYZE_API_KEY` | Recommended for Siege |
| `UBISOFT_EMAIL` / `UBISOFT_PASSWORD` | Optional if Arenyze is set |
| `R6_PLAYER_1_NAME` … `_3_NAME` | In-game names |
| `R6_PLAYER_1_PLATFORM` … `_3_PLATFORM` | `pc`, `psn`, or `xbox` (default `pc`) |
| `FN_PLAYER_1_NAME` … `_3_NAME` | Epic / PSN / Xbox display names |
| `FN_PLAYER_1_ACCOUNT_TYPE` … `_3_ACCOUNT_TYPE` | `epic`, `psn`, or `xbl` (default `epic`) |
| `FN_PLAYER_3_NAME_FALLBACK` | Optional second Fortnite name if the first 404s |

Player names never go in `stats.json`. Discord **does** show the live name in the embed.

### 5. Run it once

**Actions → Track player stats → Run workflow**

The first successful fetch is a **silent baseline** (no Discord spam from `0 → real stats`). After that, the cron job posts only when a tracked number changes, and commits the new `stats.json`.

Scheduled workflows stay off on a brand-new public repo until that first manual run.

### 6. Make the 15-minute check actually on time (one-time)

GitHub's own cron on a **public** repo is often 1–2 hours late. Discord still posts in the same run as soon as a stat changes — the check just does not start on time.

Keep using GitHub Actions as the host. Add a free [cron-job.org](https://cron-job.org) job that presses **Run workflow** every 15 minutes:

1. Create a [fine-grained PAT](https://github.com/settings/personal-access-tokens/new): only this repo, permission **Actions: Read and write**, expiration 1 year. Copy it once. Do not commit it.
2. On [cron-job.org](https://cron-job.org) → Create cronjob:
   - Title: `r6-fn tracker`
   - Address: `https://api.github.com/repos/Squiddoo/r6-fn-discord-tracker/actions/workflows/workflow.yml/dispatches`
   - Schedule: every 15 minutes
   - Request method: `POST`
   - Headers:
     - `Accept: application/vnd.github+json`
     - `Authorization: Bearer <paste-the-PAT>`
     - `X-GitHub-Api-Version: 2022-11-28`
     - `Content-Type: application/json`
   - Body: `{"ref":"main"}`
3. Click **Test run**. You should see a new run under **Actions** within a few seconds.

After that you can leave it. Renew the PAT when it expires.

---

## What gets posted

One Discord embed per player who changed:

- **Siege:** ranked / casual / overall (rank, RP, kills, deaths, wins, K/D, level, hours)
- **Fortnite:** this-season **BR rank** and **Reload rank**, career wins, eliminations, matches, K/D, Solo/Duo/Squad wins, Battle Pass level

`stats.json` is overwritten each run. It is not a history log.

---

## Local test (optional)

GitHub Actions is the real host. Local is only for debugging.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill `.env`, then:

```bash
python -m tracker
```

(The bot loads `.env` by itself. You do not need to export variables in PowerShell.)

---

## Privacy

Safe to keep the repo **public**:

- No usernames, webhooks, or API keys in source or in `stats.json`
- Keys live in GitHub Secrets (they do **not** copy to forks)
- Discord embeds show live names only in your channel, not on GitHub

Someone who clones this gets empty placeholders. Running it without *their own* secrets does nothing to your webhook or accounts.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Workflow never runs on a schedule | Run **Track player stats** once by hand, then add the cron-job.org ping in step 6 |
| Checks are hours late | GitHub public cron delay — use the cron-job.org ping in step 6 |
| `Missing required environment variable` | A secret name does not match `.env.example` |
| Siege 429 / Ubisoft rate limit | Normal on GitHub IPs — set `ARENYZE_API_KEY` |
| Fortnite 403 / 404 | Stats are private, or the display name / account type is wrong |
| No Discord message after first run | First run is silent on purpose; wait for a real stat change |
