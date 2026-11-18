import discord
from datetime import timedelta
from typing import Optional
from discord import app_commands
from discord.ext import commands
import database as db
from utils import embed, err, log, can_act, RED

class Moderation(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name='ban', description='Banish a user from the realm')
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def ban(self, i: discord.Interaction, user: discord.User, reason: Optional[str] = 'No reason given'):
        if not can_act(i, i.guild.get_member(user.id)): return await err(i, 'My blade cannot reach that knight (role too high).')
        try: await i.guild.ban(user, reason=f'{i.user}: {reason}')
        except discord.HTTPException: return await err(i, 'I could not ban that user.')
        await log(i.guild, f'⚔️ **{user}** was banned by {i.user}. Reason: {reason}')
        await i.response.send_message(embed=embed('⚔️ Banished', f'**{user}** has been banished.\n**Reason:** {reason}'))

    @app_commands.command(name='kick', description='Expel a user from the realm')
    @app_commands.default_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(self, i: discord.Interaction, user: discord.Member, reason: Optional[str] = 'No reason given'):
        if not can_act(i, user): return await err(i, 'My blade cannot reach that knight (role too high).')
        try: await user.kick(reason=f'{i.user}: {reason}')
        except discord.HTTPException: return await err(i, 'I could not kick that user.')
        await log(i.guild, f'👢 **{user}** was kicked by {i.user}. Reason: {reason}')
        await i.response.send_message(embed=embed('👢 Expelled', f'**{user}** has been expelled.\n**Reason:** {reason}'))

    @app_commands.command(name='timeout', description='Send a user to the dungeon (timeout)')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def timeout(self, i: discord.Interaction, user: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: Optional[str] = 'No reason given'):
        if not can_act(i, user): return await err(i, 'I cannot timeout that knight.')
        try: await user.timeout(timedelta(minutes=minutes), reason=reason)
        except discord.HTTPException: return await err(i, 'I could not timeout that user.')
        await log(i.guild, f'⏳ **{user}** timed out for {minutes}m by {i.user}. {reason}')
        await i.response.send_message(embed=embed('⏳ Dungeon', f'**{user}** is locked away for **{minutes}** minutes.\n**Reason:** {reason}'))

    @app_commands.command(name='untimeout', description='Free a user from the dungeon')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def untimeout(self, i: discord.Interaction, user: discord.Member):
        await user.timeout(None)
        await i.response.send_message(embed=embed('🗝️ Freed', f'**{user}** has been released.'))

    @app_commands.command(name='warn', description='Issue a warning')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warn(self, i: discord.Interaction, user: discord.Member, reason: str):
        n = db.add_warn(i.guild.id, user.id, i.user.id, reason)
        try: await user.send(embed=embed(f'⚠️ Warning from {i.guild.name}', reason, RED))
        except discord.HTTPException: pass
        await log(i.guild, f'⚠️ **{user}** warned by {i.user}: {reason}')
        await i.response.send_message(embed=embed('⚠️ Warning issued', f'**{user}** now has **{n}** warning(s).\n**Reason:** {reason}'))

    @app_commands.command(name='warnings', description="View a user's warnings")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warnings(self, i: discord.Interaction, user: discord.Member):
        rows = db.many('SELECT * FROM warns WHERE guild=? AND user=? ORDER BY id DESC LIMIT 10', (str(i.guild.id), str(user.id)))
        text = '\n'.join(f"**#{w['id']}** <t:{w['ts'] // 1000}:R> — {w['reason']}" for w in rows) or 'A spotless record.'
        await i.response.send_message(embed=embed(f'📜 Warnings: {user}', text))

    @app_commands.command(name='clearwarns', description='Clear all warnings of a user')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def clearwarns(self, i: discord.Interaction, user: discord.Member):
        db.run('DELETE FROM warns WHERE guild=? AND user=?', (str(i.guild.id), str(user.id)))
        await i.response.send_message(embed=embed('🧹 Record cleansed', f'All warnings for **{user}** were cleared.'))

    @app_commands.command(name='purge', description='Delete recent messages')
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def purge(self, i: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        await i.response.defer(ephemeral=True)
        deleted = await i.channel.purge(limit=amount)
        await i.followup.send(embed=embed('🧹 Purged', f'Swept away **{len(deleted)}** messages.'))

    @app_commands.command(name='slowmode', description='Set channel slowmode (0 = off)')
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def slowmode(self, i: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
        await i.channel.edit(slowmode_delay=seconds)
        await i.response.send_message(embed=embed('🐢 Slowmode', f'Set to **{seconds}s**.'))

    async def _lock(self, i, lock):
        ow = i.channel.overwrites_for(i.guild.default_role)
        ow.send_messages = False if lock else None
        await i.channel.set_permissions(i.guild.default_role, overwrite=ow)
        await i.response.send_message(embed=embed('🔒 Gates closed' if lock else '🔓 Gates open', f'Channel {"locked" if lock else "unlocked"}.'))

    @app_commands.command(name='lock', description='Lock this channel')
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def lock(self, i: discord.Interaction): await self._lock(i, True)

    @app_commands.command(name='unlock', description='Unlock this channel')
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def unlock(self, i: discord.Interaction): await self._lock(i, False)

async def setup(bot): await bot.add_cog(Moderation(bot))
