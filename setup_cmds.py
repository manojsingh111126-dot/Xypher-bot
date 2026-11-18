import discord
from typing import Optional, Literal
from discord import app_commands
from discord.ext import commands
import database as db
from utils import embed

PERM = discord.Permissions(manage_guild=True)

class Setup(commands.Cog):
    setup = app_commands.Group(name='setup', description='Configure Xypher', default_permissions=PERM, guild_only=True)
    automod = app_commands.Group(name='automod', description='Configure auto-moderation', default_permissions=PERM, guild_only=True)

    def __init__(self, bot): self.bot = bot

    async def _ok(self, i, what):
        await i.response.send_message(embed=embed('⚙️ Saved', f'The **{what}** settings have been updated.'))

    @setup.command(name='welcome', description='Set the welcome channel and message ({user} {server} {count})')
    async def welcome(self, i: discord.Interaction, channel: discord.TextChannel, message: Optional[str] = None):
        patch = {'welcomeChannel': str(channel.id)}
        if message: patch['welcomeMsg'] = message
        db.set_settings(i.guild.id, patch); await self._ok(i, 'welcome')

    @setup.command(name='logs', description='Set the mod-log channel')
    async def logs(self, i: discord.Interaction, channel: discord.TextChannel):
        db.set_settings(i.guild.id, {'logChannel': str(channel.id)}); await self._ok(i, 'logs')

    @setup.command(name='autorole', description='Role given to new members')
    async def autorole(self, i: discord.Interaction, role: discord.Role):
        db.set_settings(i.guild.id, {'autorole': str(role.id)}); await self._ok(i, 'autorole')

    @setup.command(name='tickets', description='Ticket category and support role')
    async def tickets(self, i: discord.Interaction, category: discord.CategoryChannel, role: Optional[discord.Role] = None):
        db.set_settings(i.guild.id, {'ticketCategory': str(category.id), 'supportRole': str(role.id) if role else None}); await self._ok(i, 'tickets')

    @automod.command(name='toggle', description='Enable or disable a filter')
    async def toggle(self, i: discord.Interaction, filter: Literal['links', 'spam', 'badwords', 'mentions'], enabled: bool):
        db.set_settings(i.guild.id, {'automod': {filter: enabled}})
        await i.response.send_message(embed=embed('🛡️ Automod', f'**{filter}** is now **{"ON" if enabled else "OFF"}**.'))

    @automod.command(name='word', description='Add or remove a banned word')
    async def word(self, i: discord.Interaction, action: Literal['add', 'remove'], word: str):
        words, w = db.get_settings(i.guild.id)['automod']['words'], word.lower().strip()
        words = sorted(set(words) | {w}) if action == 'add' else [x for x in words if x != w]
        db.set_settings(i.guild.id, {'automod': {'words': words}})
        await i.response.send_message(embed=embed('🛡️ Automod', 'Banned words: ' + (', '.join(f'||{x}||' for x in words) or 'none')), ephemeral=True)

async def setup(bot): await bot.add_cog(Setup(bot))
