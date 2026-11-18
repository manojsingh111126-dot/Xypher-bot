import re, time, discord
from collections import defaultdict, deque
from datetime import timedelta
from discord.ext import commands
import database as db
from utils import embed, log, RED

class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.hits = defaultdict(lambda: deque(maxlen=6))

    @commands.Cog.listener()
    async def on_message(self, m: discord.Message):
        if not m.guild or m.author.bot or not isinstance(m.author, discord.Member): return
        if m.author.guild_permissions.manage_messages: return
        a, text, reason = db.get_settings(m.guild.id)['automod'], m.content.lower(), None
        if a['links'] and re.search(r'(https?://|discord\.gg/|www\.)', text): reason = 'Posting links'
        elif a['badwords'] and any(re.search(rf'\b{re.escape(w)}\b', text) for w in a['words']): reason = 'Banned word'
        elif a['mentions'] and len(m.mentions) >= 5: reason = 'Mass mentions'
        elif a['spam']:
            q = self.hits[(m.guild.id, m.author.id)]; now = time.time(); q.append(now)
            if len(q) >= 6 and now - q[0] < 5: reason = 'Spamming'; q.clear()
        if not reason: return
        try: await m.delete()
        except discord.HTTPException: pass
        n = db.add_warn(m.guild.id, m.author.id, self.bot.user.id, f'[Automod] {reason}')
        await m.channel.send(embed=embed('🛡️ Automod', f'{m.author.mention}, **{reason}** is not tolerated here. Warning **{n}/{a["maxWarns"]}**.', RED), delete_after=6)
        await log(m.guild, f'🛡️ Automod: **{m.author}** — {reason} (warn {n})')
        if n >= a['maxWarns']:
            try: await m.author.timeout(timedelta(minutes=10), reason='Automod: too many warnings')
            except discord.HTTPException: pass

async def setup(bot): await bot.add_cog(AutoMod(bot))
