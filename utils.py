import time, discord
import database as db

GOLD, RED, STEEL, NIGHT = 0xC9A227, 0xB03A2E, 0x7B8794, 0x171B22
COIN, COINS = '🪙', 'Xycoins'

def embed(title, desc=None, color=GOLD):
    """Build every bot message with the Xypher night-castle visual identity."""
    e = discord.Embed(title=title, description=desc, color=color or GOLD)
    e.set_footer(text='Xypher • Knight of the Realm ⚔️')
    e.timestamp = discord.utils.utcnow()
    return e

def fmt(n): return f'{int(n):,}'

async def err(i: discord.Interaction, text):
    await i.response.send_message(embed=embed('🛡️ Halt, knight', text, RED), ephemeral=True)

async def log(guild: discord.Guild, text):
    db.run('INSERT INTO logs(guild,text,ts) VALUES(?,?,?)', (str(guild.id), text, int(time.time() * 1000)))
    cid = db.get_settings(guild.id)['logChannel']
    ch = guild.get_channel(int(cid)) if cid else None
    if ch:
        try: await ch.send(embed=embed('📜 Royal Ledger', text, STEEL))
        except discord.HTTPException: pass

def can_act(i: discord.Interaction, m: discord.Member | None):
    """Role-hierarchy check for moderation commands."""
    if m is None: return True
    if m == i.guild.owner or m.top_role >= i.guild.me.top_role: return False
    return i.user == i.guild.owner or m.top_role < i.user.top_role
