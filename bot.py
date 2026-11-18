import os, asyncio, discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
import database as db
from utils import embed, RED

db.init()
EXTENSIONS = ['moderation', 'utility', 'fun', 'economy', 'tickets', 'automod', 'welcome', 'setup_cmds']

class Xypher(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)

    async def setup_hook(self):
        for ext in EXTENSIONS:
            await self.load_extension(ext)
        gid = os.getenv('GUILD_ID')
        if gid:
            g = discord.Object(int(gid))
            self.tree.copy_global_to(guild=g)
            await self.tree.sync(guild=g)
        else:
            await self.tree.sync()
        if os.getenv('RUN_DASHBOARD', '1') == '1':
            import subprocess, sys, atexit
            proc = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboard.py')])
            atexit.register(proc.terminate)

    async def on_ready(self):
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='over the realm ⚔️'))
        print(f'⚔️  Xypher online as {self.user} • {len(self.tree.get_commands())} commands')

bot = Xypher()

@bot.tree.error
async def on_tree_error(i: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = 'You lack the rank for that command.'
    elif isinstance(error, app_commands.BotMissingPermissions):
        msg = 'I lack the permissions to do that.'
    else:
        msg = 'Something broke while running that command.'
        print('Command error:', repr(error))
    e = embed('🛡️ Halt, knight', msg, RED)
    if i.response.is_done(): await i.followup.send(embed=e, ephemeral=True)
    else: await i.response.send_message(embed=e, ephemeral=True)

if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token: raise SystemExit('Missing DISCORD_TOKEN in .env')
    bot.run(token)
