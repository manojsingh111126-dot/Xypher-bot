# ⚔️ Xypher — Knight of the Realm

A dark, gold-accented Discord bot and Castle Command dashboard.

**Modules:** Moderation · Utility · Fun & Actions · Xycoins economy · Tickets · AutoMod · Welcome · Discord OAuth dashboard

Requires Python 3.10+. Keep all project files in the same folder.

## Project files

- `bot.py` — main bot entry point (renamed from `main.py`)
- `dashboard.py` — NiceGUI web dashboard
- `database.py` — shared SQLite storage
- `utils.py` — shared knight-themed Discord embeds and helpers
- `moderation.py`, `utility.py`, `fun.py`, `economy.py`, `tickets.py`, `automod.py`, `welcome.py`, `setup_cmds.py` — bot modules
- `requirements.txt` — dependencies
- `.env.example` — environment-variable template

## 1. Discord Developer Portal

1. Create or select your Discord application and copy its Application ID into `CLIENT_ID`.
2. In the Bot tab, copy the bot token into `DISCORD_TOKEN`.
3. Enable **Server Members Intent** and **Message Content Intent** if your enabled features need them.
4. In OAuth2, copy the Client Secret into `CLIENT_SECRET`.
5. Add this redirect URL under OAuth2 → Redirects: `https://YOUR-DASHBOARD-DOMAIN/callback`.
6. Invite the bot with `bot` and `applications.commands` scopes and the permissions your chosen modules need.

## 2. Configure and launch

1. Upload/extract all project files into one folder.
2. Copy `.env.example` to `.env` and fill in the values. Never share your `.env` or bot token.
3. Set `DASHBOARD_URL` to your public dashboard URL (HTTPS, without a trailing slash).
4. Install dependencies:

   `pip install -r requirements.txt`

5. Set your hosting startup command to:

   `python bot.py`

`bot.py` starts the Discord bot and, when `RUN_DASHBOARD=1`, starts `dashboard.py` as a companion process. Both processes use the same `xypher.db` file. The dashboard listens on `SERVER_PORT`, `PORT`, or `DASHBOARD_PORT` (default `8080`).

To run only the bot, set `RUN_DASHBOARD=0`. To run the dashboard separately, start `python dashboard.py` from the same folder and make sure it uses the same database.

## 3. Dashboard

The dashboard keeps the Xypher knight identity: deep night surfaces, muted steel borders, and royal-gold highlights. It includes:

- Discord OAuth login and server selection
- Per-server overview and setup checklist
- Welcome channel, autorole, message editor, and live preview
- AutoMod switches, warning threshold, and word list
- Ticket insights, searchable ticket list, ticket detail/transcript view
- Ticket settings and panel designer/deployer
- Xycoins leaderboard and royal ledger / warnings

Only servers where the signed-in user has Manage Server (or is owner/Administrator) are listed as manageable. Xypher must also be present in a server before its dashboard settings can be opened.

## 4. Discord message styling

Bot-generated embeds use the shared Xypher visual identity and footer: **Xypher • Knight of the Realm ⚔️**. Welcome messages, ticket panels, ticket updates, moderation responses, economy responses, and logs use the common embed helper where applicable. User-authored message text remains editable and is not forcibly rewritten.

## 5. Tickets

Ticket categories become buttons. Members submit a subject and details form. Tickets receive numbered private channels and support claim, priority, add/remove user, close-with-reason, transcript, and rating flows. Transcripts can be stored and sent to the configured log channel and user DM.

## 6. First-time setup

Use dashboard settings or commands such as `/setup welcome`, `/setup logs`, `/setup autorole`, `/setup tickets`, `/ticket panel`, and `/automod toggle`.

Set `GUILD_ID` in `.env` while testing if you want faster guild-scoped slash-command synchronization. Remove it for global command sync.

## Commands

**Moderation:** ban, kick, timeout, untimeout, warn, warnings, clearwarns, purge, slowmode, lock, unlock

**Utility:** ping, avatar, userinfo, serverinfo, help

**Economy:** balance, daily, work, deposit, withdraw, pay, gamble, leaderboard

**Actions:** hug, kiss, pat, slap, dance, cry, poke, wave, cuddle, highfive, bite, laugh

**Fun:** 8ball, coinflip, roll, joust

**Tickets:** ticket panel

**Setup:** setup …, automod …
