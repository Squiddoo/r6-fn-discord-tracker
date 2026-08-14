# R6 + Fortnite Discord stats tracker

GitHub Actions bot that checks Rainbow Six Siege and Fortnite stats every 15 minutes, compares them to the last snapshot, and posts a Discord embed when anything changed.

`stats.json` is a **current-state snapshot only**. Each successful run **overwrites** the file. It never appends history, never stores usernames, and only keeps these six anonymous keys:

- `player_1_r6`, `player_2_r6`, `player_3_r6`
- `player_1_fn`, `player_2_fn`, `player_3_fn`

Real names exist only in GitHub Secrets and in memory while the job runs.

## What it tracks

Rainbow Six (ranked + overall, plus casual ranks):

- Ranked rank, rank points, kills, deaths, wins, K/D
- Casual rank, MMR, kills, deaths, wins, K/D
- Overall kills, deaths, wins, K/D
- Account level and hours played

Fortnite (lifetime, all inputs combined):

- Victory Royales, eliminations, matches, K/D
- Solo / Duo / Squad wins
- Battle Pass level

Fortnite-API.com does not expose Ranked BR tiers (Unreal, Champion, and so on). Mode wins are included instead.

## APIs

| Game | Source | Secret |
| --- | --- | --- |
| Rainbow Six Siege | [`siegeapi`](https://github.com/CNDRD/siegeapi) (Ubisoft, primary) | `UBISOFT_EMAIL`, `UBISOFT_PASSWORD` |
| Rainbow Six fallback | [Arenyze](https://r6.arenyze.com/api-docs) | `ARENYZE_API_KEY` |
| Fortnite | [fortnite-api.com](https://fortnite-api.com/) | `FORTNITE_API_KEY` |

Keep Ubisoft and Arenyze credentials in `.env` / GitHub Secrets only. Never commit them. Fortnite career stats must be public. If Ubisoft rate-limits or login fails, the bot falls back to Arenyze.

The GitHub Actions workflow runs every 15 minutes (`*/15 * * * *`) and can also be started by hand. The first run after clone is a silent baseline so Discord is not spammed with `0 → real`.

## GitHub Secrets

Create a Discord webhook, then add these repository secrets:

| Secret | Example |
| --- | --- |
| `DISCORD_WEBHOOK_URL` | `https://discord.com/api/webhooks/...` |
| `FORTNITE_API_KEY` | from fortnite-api.com |
| `UBISOFT_EMAIL` | Ubisoft login email |
| `UBISOFT_PASSWORD` | Ubisoft login password |
| `ARENYZE_API_KEY` | optional; r6.arenyze.com fallback |
| `R6_PLAYER_1_NAME` | Ubisoft username |
| `R6_PLAYER_1_PLATFORM` | `pc`, `psn`, or `xbox` |
| `R6_PLAYER_2_NAME` | |
| `R6_PLAYER_2_PLATFORM` | |
| `R6_PLAYER_3_NAME` | |
| `R6_PLAYER_3_PLATFORM` | |
| `FN_PLAYER_1_NAME` | Epic / PSN / Xbox display name |
| `FN_PLAYER_1_ACCOUNT_TYPE` | `epic`, `psn`, or `xbl` |
| `FN_PLAYER_2_NAME` | |
| `FN_PLAYER_2_ACCOUNT_TYPE` | |
| `FN_PLAYER_3_NAME` | |
| `FN_PLAYER_3_NAME_FALLBACK` | Optional second Fortnite name if the primary 404s |
| `FN_PLAYER_3_ACCOUNT_TYPE` | |

Platform / account-type secrets can be omitted; they default to `pc` and `epic`.

## How a run works

1. Cron `*/15 * * * *` (or **Run workflow**).
2. Read `stats.json`.
3. Fetch live stats. A failed player keeps their previous snapshot values.
4. If a player changed **and** they already had a real baseline, send **one Discord embed for that player**.
5. The first real fetch for a zeroed player is saved silently so the channel is not spammed with `0 → 1234`.
6. **Overwrite** `stats.json` with the current 6-player object (no log, no history array).
7. Commit and push `stats.json` only when the snapshot actually changed.

Scheduled workflows stay off on a new public repo until Actions has been used once. After the first push, open the **Actions** tab and run **Track player stats** manually.

## Local run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill `.env`, then:

```bash
# PowerShell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
  $name, $value = $_.Split('=', 2)
  Set-Item -Path "Env:$name" -Value $value
}
python -m tracker
```

## Privacy

- No usernames, IDs, webhooks, or API keys in source or in `stats.json`.
- Discord embeds **do** show the live username, because that message is not in the public repo.
