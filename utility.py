import discord
from typing import Optional
from discord import app_commands
from discord.ext import commands
from utils import embed, COIN, COINS

class Utility(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name='ping', description="Check the bot's latency")
    async def ping(self, i: discord.Interaction):
        await i.response.send_message(embed=embed('🏓 Pong', f'Latency: **{round(self.bot.latency * 1000)}ms**'))

    @app_commands.command(name='avatar', description='Show an avatar')
    async def avatar(self, i: discord.Interaction, user: Optional[discord.User] = None):
        u = user or i.user
        await i.response.send_message(embed=embed(f'🖼️ {u.display_name}').set_image(url=u.display_avatar.with_size(512).url))

    @app_commands.command(name='userinfo', description='Show info about a knight')
    @app_commands.guild_only()
    async def userinfo(self, i: discord.Interaction, user: Optional[discord.Member] = None):
        m = user or i.user
        roles = ' '.join(r.mention for r in m.roles if r != i.guild.default_role) or 'None'
        e = embed(f'🛡️ {m}', f'**ID:** {m.id}\n**Created:** <t:{int(m.created_at.timestamp())}:R>\n**Joined:** <t:{int(m.joined_at.timestamp())}:R>\n**Roles:** {roles}')
        await i.response.send_message(embed=e.set_thumbnail(url=m.display_avatar.url))

    @app_commands.command(name='serverinfo', description='Show info about this kingdom')
    @app_commands.guild_only()
    async def serverinfo(self, i: discord.Interaction):
        g = i.guild
        e = embed(f'🏰 {g.name}', f'**Knights:** {g.member_count}\n**Channels:** {len(g.channels)}\n**Roles:** {len(g.roles)}\n**Founded:** <t:{int(g.created_at.timestamp())}:D>\n**Owner:** {g.owner.mention if g.owner else "Unknown"}')
        if g.icon: e.set_thumbnail(url=g.icon.url)
        await i.response.send_message(embed=e)

    @app_commands.command(name='help', description="List all of Xypher's commands")
    async def help(self, i: discord.Interaction):
        text = '\n'.join([
            '**🛡️ Moderation:** `ban kick timeout untimeout warn warnings clearwarns purge slowmode lock unlock`',
            '**🏰 Utility:** `ping avatar userinfo serverinfo help`',
            f'**{COIN} Economy:** `balance daily work deposit withdraw pay gamble leaderboard`',
            '**🎭 Actions:** `hug kiss pat slap dance cry poke wave cuddle highfive bite laugh`',
            '**🎲 Fun:** `8ball coinflip roll joust`',
            '**🎫 Tickets:** `ticket panel`',
            '**⚙️ Setup:** `setup welcome | logs | autorole | tickets` • `automod toggle | word`',
        ])
        await i.response.send_message(embed=embed('⚔️ Xypher — Command Codex', text))

async def setup(bot): await bot.add_cog(Utility(bot))
