# ⚔️ Xypher — Knight-themed Discord Bot

Moderation • AutoMod • Economy (**Xycoins**) • Casino • Mini-games • Actions (42 GIF actions) • Leveling •
Welcome & verification • Tickets • VoiceMaster (chambers) • Utility • AI chat • Web dashboard (Login with Discord)

## Run it
1. Python 3.10+, then: `pip install -r requirements.txt`
2. Set environment variables (host "Variables" tab, or a `.env` file next to `bot.py` — see `.env.example`):
   - `DISCORD_TOKEN`  — Developer Portal → Bot → Reset Token
   - `CLIENT_SECRET`  — Developer Portal → OAuth2 → Client Secret
   - `REDIRECT_URI`   — `https://xypherbot.fadehost.app/auth/callback`
   - optional: `DASHBOARD_PORT`, `OWNER_ID`, `GROQ_API_KEY`, `GEMINI_API_KEY`
3. Start command: `python bot.py` (or `python main.py`)

## Developer Portal checklist
- Bot tab → turn ON **Server Members Intent** and **Message Content Intent**.
- OAuth2 → Redirects → add exactly `https://xypherbot.fadehost.app/auth/callback` and press **Save Changes**.
- Invite with scopes `bot` + `applications.commands` (Administrator is easiest).
- In Server Settings → Roles, drag Xypher's role **above** the roles it must moderate.
- Optional: upload `xypher-logo.png` as the bot's avatar.

## Xypher vs. the rest — what's knightly
- Currency is **Xycoins 🪙**: `/balance /daily /work /give /richest`, `/treasury weekly|deposit|withdraw|plunder|use`,
  armory `/shop /buy /inventory` (Iron Lock, War Horn, Knight's Helm, Golden Grail, Royal Crown…)
- Knight commands: `/lore /charge /joust /dub` (+ `/ping /avatar`)
- Casino = tavern games: `/slots /blackjack /mines /coinflip`, `/casino hilo|roulette|dice|rps`
- Mini-games with knight & medieval trivia: `/game trivia|daily|hangman|tictactoe|connect4|rps|catch`, `/guess`
- Moderation, AutoMod, Leveling, Welcome, Tickets, VoiceMaster, Utility, Actions: same powerful feature set, re-themed.
- Dashboard: castle background, rose-window decor, gallop-ing knight loader, golden theme.
