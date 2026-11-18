# ⚔️ Xypher — Knight-themed Discord Bot (Python) + Dashboard

Moderation • Utility • Fun & Actions • Economy (**Xycoins**) • Tickets • Automod • Welcome • Web dashboard with **Login with Discord**.
Requires **Python 3.10+**. All files live in one flat folder.

## Files
`main.py` (bot) · `dashboard.py` (pure-Python website built with NiceGUI — no HTML files) · `database.py`, `utils.py` · cogs: `moderation.py utility.py fun.py economy.py tickets.py automod.py welcome.py setup_cmds.py` · `requirements.txt` · `.env.example`

## 1. Discord Developer Portal
1. Create/select your application **Xypher**. Copy the **Application ID** (CLIENT_ID).
2. **Bot** tab → Reset Token (DISCORD_TOKEN). Enable **Server Members Intent** and **Message Content Intent**.
3. **OAuth2** tab → copy **Client Secret** (CLIENT_SECRET).
4. **OAuth2 → Redirects** → add exactly: `https://YOUR-DASHBOARD-DOMAIN/callback`
   (e.g. `https://spideydashboard.fadehost.app/callback`). It must match `DASHBOARD_URL` + `/callback`.
5. Invite the bot with scopes `bot` + `applications.commands` and Administrator (or the needed permissions).

## 2. Host it (FadeHost or any Python host)
1. Upload all files into the server's root directory (no sub-folders).
2. Rename `.env.example` → `.env` and fill it in. Set `DASHBOARD_URL` to your real domain (https, no trailing slash).
3. Install: `pip install -r requirements.txt` (many hosts do this automatically from requirements.txt).
4. Startup file / command: `python main.py`
   This starts the bot and launches the dashboard alongside it (shared `xypher.db`). The dashboard listens on the host's `SERVER_PORT`/`PORT` automatically.
   The dashboard uses WebSockets, so the host/proxy must allow them (normal on FadeHost-style direct ports).
5. Point your domain / allocated port to the dashboard. Open it → **Login with Discord**.

> Bot and dashboard must run on the same host/container because they share the SQLite file.
> To run the dashboard alone, set `RUN_DASHBOARD=0` for the bot and start `python dashboard.py` next to the same `xypher.db`.

## Tickets
Categories as buttons, subject/details form, numbered channels, claim, priority, add/remove users, close with reason, transcripts (saved + sent to log channel + DM), 1–5★ ratings. In the dashboard: insights & charts, searchable ticket table with full transcripts, settings, and a panel designer that deploys the panel to any channel.

## 3. Using it
Anyone with **Manage Server** (or Administrator/owner) in a server where Xypher is present can edit that server in the dashboard. Servers without Xypher show an **Invite** button.

First-time commands (or use the dashboard): `/setup welcome`, `/setup logs`, `/setup autorole`, `/setup tickets`, `/ticket panel`, `/automod toggle`.
Set `GUILD_ID` in `.env` while testing so slash commands appear instantly (global sync can take up to an hour).

## Commands
Moderation: ban kick timeout untimeout warn warnings clearwarns purge slowmode lock unlock • Utility: ping avatar userinfo serverinfo help • Economy: balance daily work deposit withdraw pay gamble leaderboard • Actions: hug kiss pat slap dance cry poke wave cuddle highfive bite laugh • Fun: 8ball coinflip roll joust • Tickets: ticket panel • Setup: setup …, automod …
