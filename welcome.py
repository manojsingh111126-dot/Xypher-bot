import discord
from discord.ext import commands
import database as db
from utils import embed, log

class Welcome(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, m: discord.Member):
        s = db.get_settings(m.guild.id)
        role = m.guild.get_role(int(s['autorole'])) if s['autorole'] else None
        if role:
            try: await m.add_roles(role, reason='Xypher autorole')
            except discord.HTTPException: pass
        ch = m.guild.get_channel(int(s['welcomeChannel'])) if s['welcomeChannel'] else None
        if ch:
            text = s['welcomeMsg'].replace('{user}', m.mention).replace('{server}', m.guild.name).replace('{count}', str(m.guild.member_count))
            try: await ch.send(embed=embed('🏰 A new knight arrives!', text).set_thumbnail(url=m.display_avatar.url))
            except discord.HTTPException: pass
        await log(m.guild, f'📥 **{m}** joined the realm.')

    @commands.Cog.listener()
    async def on_member_remove(self, m: discord.Member):
        await log(m.guild, f'📤 **{m}** left the realm.')

async def setup(bot): await bot.add_cog(Welcome(bot))
