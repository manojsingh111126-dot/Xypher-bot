import os
import random
import traceback

import discord
from discord import app_commands
from discord.ext import commands

# ---------- ENVIRONMENT (works with host variables AND/OR a .env file, no extra package needed) ----------
def _load_env():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8-sig"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().removeprefix("export ").strip()
            os.environ.setdefault(k, v.strip().strip("\"'"))
    # clean names/values (stray spaces, quotes, lower-case names)
    for k, v in list(os.environ.items()):
        nk, nv = k.strip().upper(), v.strip().strip("\"'")
        if nk != k or nv != v:
            os.environ.setdefault(nk, nv)
            os.environ[nk] = nv if nk == k else os.environ.get(nk, nv)
    # accept common alternative names
    alias = {
        "DISCORD_TOKEN": ["TOKEN", "BOT_TOKEN"],
        "CLIENT_SECRET": ["DISCORD_CLIENT_SECRET", "OAUTH_CLIENT_SECRET", "CLIENT_SECRET_KEY"],
        "REDIRECT_URI": ["REDIRECT_URL", "DASHBOARD_REDIRECT_URI", "OAUTH_REDIRECT_URI"],
        "GROQ_API_KEY": ["GROQ_KEY"], "GEMINI_API_KEY": ["GOOGLE_API_KEY", "GEMINI_KEY"],
    }
    for want, others in alias.items():
        if not os.environ.get(want):
            for o in others:
                if os.environ.get(o):
                    os.environ[want] = os.environ[o]
                    break
    if not os.environ.get("REDIRECT_URI"):  # build it from the dashboard's public address if only that was set
        for o in ("DASHBOARD_URL", "DASHBOARD_URI", "BASE_URL", "PUBLIC_URL"):
            if os.environ.get(o):
                os.environ["REDIRECT_URI"] = os.environ[o].rstrip("/") + "/auth/callback"
                break
    seen = {k: bool(os.environ.get(k)) for k in ("DISCORD_TOKEN", "CLIENT_SECRET", "REDIRECT_URI", "GROQ_API_KEY", "GEMINI_API_KEY")}
    print("🔎 Settings found: " + "  ".join(f"{k} {'✅' if ok else '❌'}" for k, ok in seen.items()))
    related = sorted(k for k in os.environ if any(w in k.upper() for w in ("SECRET", "REDIRECT", "URI", "URL", "CLIENT", "TOKEN", "API_KEY")))
    print("🔎 Variable NAMES your host gave me (values hidden): " + (", ".join(related) or "none"))


_load_env()

from theme import knight_embed, GOLD, DARK, STEEL, CRIMSON, install_error_handlers

install_error_handlers()  # buttons/menus/forms never fail silently

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing!")

# ---------- THEME ----------
KNIGHT_LORE = [
    "A full suit of plate armor could weigh 20–25 kg, yet knights could still mount a horse unaided. 🛡️",
    "Knights were usually trained from childhood: first a page, then a squire, then finally knighted. ⚔️",
    "The portcullis was a heavy gate that could be dropped in seconds to seal a castle. 🏰",
    "Castle spiral staircases often turned clockwise so a defender's sword arm had more room. 🗡️",
    "Heraldry gave every knight a unique coat of arms so allies could spot him in battle. 🦁",
    "A joust could be fought with blunted lances, called 'lances of courtesy'. 🐎",
    "Medieval castles often had a 'murder hole' above the gate for dropping stones on attackers. 🪨",
]
TITLES = ["the Brave", "the Bold", "the Unyielding", "Dragonslayer", "the Lionheart", "Shieldbearer",
          "the Radiant", "Ironwill", "the Just", "Stormblade", "the Steadfast", "Oathkeeper"]

# ---------- BOT SETUP ----------
intents = discord.Intents.default()
intents.members = True  # needed for welcome messages (enable in Dev Portal too)
intents.message_content = True  # needed for AutoMod (enable "Message Content Intent" in Dev Portal too)


class Xypher(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)

    async def setup_hook(self):
        await self.load_extension("voicemaster")  # 🎙️ VoiceMaster (chambers)
        await self.load_extension("moderation")   # 🛡️ Moderation
        await self.load_extension("utility")      # 🧰 Utility
        await self.load_extension("automod")      # 🤖 AutoMod
        await self.load_extension("help")         # 📖 Help (dropdown codex)
        await self.load_extension("economy")      # 🪙 Economy (Xycoins, armory)
        await self.load_extension("casino")       # 🎰 Casino (tavern games)
        await self.load_extension("leveling")     # ⭐ Leveling (XP, knight ranks)
        await self.load_extension("welcome")      # 👋 Welcome & verification
        await self.load_extension("tickets")      # 🎫 Tickets
        await self.load_extension("minigames")    # 🎲 Mini-games (/game, /guess)
        await self.load_extension("actions")      # 🤗 Actions (/hug /slap /punch /dance, /interact, /react)
        await self.load_extension("ai_chat")      # 🧠 AI Chat (@Xypher <question>)
        await self.load_extension("dashboard")    # 🖥️ Web dashboard (load LAST)

        await self.tree.sync()


client = Xypher()
tree = client.tree


@client.event
async def on_ready():
    await client.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(type=discord.ActivityType.watching, name="over the realm ⚔️"),
    )
    print(f"⚔️ Xypher stands guard as {client.user}")


# ---------- COMMANDS ----------
# Discord allows only 100 top-level slash commands per bot, so the knight commands live in ONE group: /knight lore|charge|joust|dub
knight = app_commands.Group(name="knight", description="Knightly fun: lore, charge, joust, dub")
tree.add_command(knight)

@tree.command(name="ping", description="Check how fast the royal messenger rides")
async def ping(interaction: discord.Interaction):
    ms = round(client.latency * 1000)
    await interaction.response.send_message(
        embed=knight_embed("Royal Messenger", f"My horse reached the castle in **{ms}ms** 🐎⚡")
    )


@knight.command(name="lore", description="Hear a piece of knightly lore")
async def lore(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=knight_embed("Knightly Lore", random.choice(KNIGHT_LORE), DARK)
    )


@knight.command(name="charge", description="Charge into battle alongside someone")
@app_commands.describe(user="Who do you want to charge with?")
async def charge(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message(
        embed=knight_embed(
            "For Glory!",
            f"{interaction.user.mention} raised their sword and charged beside {user.mention}! ⚔️🛡️",
        )
    )


@knight.command(name="joust", description="Challenge a knight to a joust")
@app_commands.describe(opponent="Who do you want to joust?")
async def joust(interaction: discord.Interaction, opponent: discord.Member):
    if opponent.bot or opponent.id == interaction.user.id:
        return await interaction.response.send_message(
            embed=knight_embed("Halt, Knight!", "Choose a worthy human opponent. 🛡️", DARK), ephemeral=True)
    winner, loser = random.sample([interaction.user, opponent], 2)
    blows = random.choice(["unseats", "shatters a lance against", "knocks the helm off", "sends flying"])
    await interaction.response.send_message(
        embed=knight_embed(
            "The Joust!",
            f"{interaction.user.mention} and {opponent.mention} thunder toward each other… 🐎💥\n\n"
            f"🏆 **{winner.display_name}** {blows} **{loser.display_name}** and wins the tourney!",
        )
    )


@knight.command(name="dub", description="Knight someone with a legendary title")
@app_commands.describe(user="Who deserves to be knighted?")
async def dub(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message(
        embed=knight_embed(
            "Arise, Sir Knight!",
            f"{interaction.user.mention} taps their sword on both shoulders…\n\n"
            f"👑 Arise, **Sir {user.display_name} {random.choice(TITLES)}**!",
        )
    )


@tree.command(name="avatar", description="Show someone's avatar in a golden frame")
async def avatar(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = knight_embed(f"{user.display_name}'s Avatar", color=STEEL)
    embed.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)


# ---------- THEMED ERRORS ----------
@tree.error
async def on_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        text = "You lack the rank for that command. ⚔️"
    elif isinstance(error, app_commands.BotMissingPermissions):
        text = "I'm missing permissions: " + ", ".join(error.missing_permissions)
    elif isinstance(error, app_commands.CommandOnCooldown):
        text = f"Easy, knight! Try again in {error.retry_after:.0f}s. 🛡️"
    elif isinstance(error, app_commands.CheckFailure):
        text = "You can't use that here. 🛡️"
    else:
        text = "Something went wrong. Try again in a moment 🛡️"
        traceback.print_exception(type(error), error, error.__traceback__)
    embed = knight_embed("Halt, Knight!", text, DARK)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException:
        pass  # interaction already expired


client.run(TOKEN)
