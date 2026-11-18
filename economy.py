import time, random, discord
from typing import Optional
from discord import app_commands
from discord.ext import commands
import database as db
from utils import embed, err, fmt, COIN, COINS, RED

def remaining(last, secs): return max(0, int(last + secs - time.time()))
def dur(s): return f'{s // 3600}h {s % 3600 // 60}m' if s >= 3600 else f'{s // 60}m {s % 60}s' if s >= 60 else f'{s}s'
def parse(v, maxv):
    if v.lower() == 'all': return maxv
    try: return int(v.replace(',', ''))
    except ValueError: return 0

class Economy(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name='balance', description=f'Check your {COINS}')
    @app_commands.guild_only()
    async def balance(self, i: discord.Interaction, user: Optional[discord.User] = None):
        u = user or i.user; d = db.get_user(i.guild.id, u.id)
        await i.response.send_message(embed=embed(f"{COIN} {u.display_name}'s Treasury",
            f"**Wallet:** {fmt(d['wallet'])} {COINS}\n**Bank:** {fmt(d['bank'])} {COINS}\n**Net worth:** {fmt(d['wallet'] + d['bank'])} {COINS}"))

    @app_commands.command(name='daily', description='Claim your daily royal stipend')
    @app_commands.guild_only()
    async def daily(self, i: discord.Interaction):
        d = db.get_user(i.guild.id, i.user.id); w = remaining(d['daily'], 86400)
        if w: return await err(i, f'The treasurer says return in **{dur(w)}**.')
        g = random.randint(400, 700)
        db.add_coins(i.guild.id, i.user.id, g)
        db.run('UPDATE users SET daily=? WHERE guild=? AND user=?', (time.time(), str(i.guild.id), str(i.user.id)))
        await i.response.send_message(embed=embed('👑 Royal Stipend', f'The crown grants you **{g} {COINS}**!'))

    @app_commands.command(name='work', description='Take a job around the castle')
    @app_commands.guild_only()
    async def work(self, i: discord.Interaction):
        d = db.get_user(i.guild.id, i.user.id); w = remaining(d['work'], 3600)
        if w: return await err(i, f'You are weary. Rest for **{dur(w)}**.')
        job = random.choice(['polished the armory', 'guarded the drawbridge', 'forged a sword', 'escorted a merchant', 'slew a goblin', 'tended the royal horses'])
        g = random.randint(60, 220)
        db.add_coins(i.guild.id, i.user.id, g)
        db.run('UPDATE users SET work=? WHERE guild=? AND user=?', (time.time(), str(i.guild.id), str(i.user.id)))
        await i.response.send_message(embed=embed('🔨 Honest Work', f'You {job} and earned **{g} {COINS}**.'))

    @app_commands.command(name='deposit', description='Store coins in the vault')
    @app_commands.guild_only()
    async def deposit(self, i: discord.Interaction, amount: str):
        d = db.get_user(i.guild.id, i.user.id); n = parse(amount, d['wallet'])
        if n < 1 or n > d['wallet']: return await err(i, 'Invalid amount.')
        db.run('UPDATE users SET wallet=wallet-?, bank=bank+? WHERE guild=? AND user=?', (n, n, str(i.guild.id), str(i.user.id)))
        await i.response.send_message(embed=embed('🏦 Deposited', f'**{fmt(n)} {COINS}** locked in the vault.'))

    @app_commands.command(name='withdraw', description='Take coins from the vault')
    @app_commands.guild_only()
    async def withdraw(self, i: discord.Interaction, amount: str):
        d = db.get_user(i.guild.id, i.user.id); n = parse(amount, d['bank'])
        if n < 1 or n > d['bank']: return await err(i, 'Invalid amount.')
        db.run('UPDATE users SET wallet=wallet+?, bank=bank-? WHERE guild=? AND user=?', (n, n, str(i.guild.id), str(i.user.id)))
        await i.response.send_message(embed=embed('💰 Withdrawn', f'**{fmt(n)} {COINS}** moved to your wallet.'))

    @app_commands.command(name='pay', description=f'Give {COINS} to another knight')
    @app_commands.guild_only()
    async def pay(self, i: discord.Interaction, user: discord.Member, amount: str):
        d = db.get_user(i.guild.id, i.user.id); n = parse(amount, d['wallet'])
        if user.bot or user == i.user: return await err(i, 'Invalid recipient.')
        if n < 1 or n > d['wallet']: return await err(i, 'Invalid amount or insufficient funds.')
        db.add_coins(i.guild.id, i.user.id, -n); db.add_coins(i.guild.id, user.id, n)
        await i.response.send_message(embed=embed('🤝 Tribute paid', f'**{i.user.display_name}** gave **{fmt(n)} {COINS}** to **{user.display_name}**.'))

    @app_commands.command(name='gamble', description='Wager at the tavern (45% to double)')
    @app_commands.guild_only()
    async def gamble(self, i: discord.Interaction, amount: str):
        d = db.get_user(i.guild.id, i.user.id); n = parse(amount, d['wallet'])
        if n < 1 or n > d['wallet']: return await err(i, 'Invalid amount or insufficient funds.')
        win = random.random() < 0.45
        db.add_coins(i.guild.id, i.user.id, n if win else -n)
        await i.response.send_message(embed=embed('🎉 Fortune smiles' if win else '💀 The tavern wins',
            f'You won **{fmt(n)} {COINS}**!' if win else f'You lost **{fmt(n)} {COINS}**.', 0xC9A227 if win else RED))

    @app_commands.command(name='leaderboard', description='Richest knights in the realm')
    @app_commands.guild_only()
    async def leaderboard(self, i: discord.Interaction):
        rows = db.many('SELECT user, wallet+bank t FROM users WHERE guild=? ORDER BY t DESC LIMIT 10', (str(i.guild.id),))
        medals = ['🥇', '🥈', '🥉']
        text = '\n'.join(f"{medals[n] if n < 3 else f'**{n + 1}.**'} <@{r['user']}> — {fmt(r['t'])} {COINS}" for n, r in enumerate(rows))
        await i.response.send_message(embed=embed('🏆 Hall of Fortune', text or 'No fortunes yet. Use `/daily`!'))

async def setup(bot): await bot.add_cog(Economy(bot))
