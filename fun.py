import random, aiohttp, discord
from typing import Optional
from discord import app_commands
from discord.ext import commands
from utils import embed, err, COIN

ACTIONS = {'hug': 'hugs', 'kiss': 'kisses', 'pat': 'pats', 'slap': 'slaps', 'dance': 'dances with', 'cry': 'cries with',
           'poke': 'pokes', 'wave': 'waves at', 'cuddle': 'cuddles', 'highfive': 'high-fives', 'bite': 'bites', 'laugh': 'laughs with'}

def make_action(name, verb):
    async def callback(i: discord.Interaction, user: Optional[discord.User] = None):
        await i.response.defer()
        url = None
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f'https://nekos.best/api/v2/{name}', timeout=aiohttp.ClientTimeout(total=6)) as r:
                    url = (await r.json())['results'][0]['url']
        except Exception:
            pass
        target = user.display_name if user else 'the air'
        e = embed(f'⚔️ {i.user.display_name} {verb} {target}!')
        if url: e.set_image(url=url)
        await i.followup.send(embed=e)
    return app_commands.Command(name=name, description=f'{name.title()} someone', callback=callback)

class Fun(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name='8ball', description='Consult the royal oracle')
    async def eightball(self, i: discord.Interaction, question: str):
        a = ['It is certain, my liege.', 'Without a doubt.', 'The stars say yes.', 'Ask again after the feast.',
             'The oracle is silent.', 'Do not count on it.', 'My sources say no.', 'Very doubtful.']
        await i.response.send_message(embed=embed('🔮 The Oracle speaks', f'**Q:** {question}\n**A:** {random.choice(a)}'))

    @app_commands.command(name='coinflip', description='Flip a royal coin')
    async def coinflip(self, i: discord.Interaction):
        await i.response.send_message(embed=embed(f'{COIN} The coin lands…', random.choice(['**Crown** 👑', '**Shield** 🛡️'])))

    @app_commands.command(name='roll', description='Roll a die')
    async def roll(self, i: discord.Interaction, sides: app_commands.Range[int, 2, 1000] = 6):
        await i.response.send_message(embed=embed('🎲 Dice roll', f'You rolled **{random.randint(1, sides)}**.'))

    @app_commands.command(name='joust', description='Challenge a knight to a joust')
    async def joust(self, i: discord.Interaction, opponent: discord.User):
        if opponent.bot or opponent == i.user: return await err(i, 'Choose a worthy opponent.')
        w = random.choice([i.user, opponent])
        await i.response.send_message(embed=embed('🐎 Joust!', f'**{i.user.display_name}** and **{opponent.display_name}** charge at each other…\n\n🏆 **{w.display_name}** unseats their foe and wins the tourney!'))

async def setup(bot):
    await bot.add_cog(Fun(bot))
    for name, verb in ACTIONS.items():
        bot.tree.add_command(make_action(name, verb))
