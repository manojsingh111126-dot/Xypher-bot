"""Full-featured ticket system: categories, modals, claim, priority, transcripts, ratings, logs."""
import io, re, time, asyncio, discord
from typing import Literal
from discord import app_commands
from discord.ext import commands
import database as db
from utils import embed, err, log, RED, STEEL

PRI = {'low': '🟢 Low', 'normal': '🔵 Normal', 'high': '🟠 High', 'urgent': '🔴 Urgent'}
now = lambda: int(time.time() * 1000)
slug = lambda s: re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:20] or 'ticket'

def is_staff(member, s):
    r = s['supportRole']
    return member.guild_permissions.manage_messages or bool(r and any(str(x.id) == str(r) for x in member.roles))

def ticket_row(channel_id): return db.one('SELECT * FROM tickets WHERE channel=?', (str(channel_id),))

def controls():
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label='Claim', emoji='🙋', style=discord.ButtonStyle.success, custom_id='tk:claim'))
    v.add_item(discord.ui.Button(label='Close', emoji='🔒', style=discord.ButtonStyle.danger, custom_id='tk:close'))
    return v

def panel_view(types):
    v = discord.ui.View(timeout=None)
    for t in types[:5]:
        v.add_item(discord.ui.Button(label=t['label'][:80], emoji=t.get('emoji') or None, style=discord.ButtonStyle.primary, custom_id=f"tk:open:{t['key']}"))
    return v

def rating_view(tid):
    v = discord.ui.View(timeout=None)
    for n in range(1, 6):
        v.add_item(discord.ui.Button(label=str(n), emoji='⭐', style=discord.ButtonStyle.secondary, custom_id=f'tk:rate:{tid}:{n}'))
    return v

class OpenModal(discord.ui.Modal):
    def __init__(self, t):
        super().__init__(title=f"{t['label']} ticket"[:45])
        self.t = t
        self.subject = discord.ui.TextInput(label='Subject', placeholder='A short summary', max_length=100)
        self.details = discord.ui.TextInput(label='Details', style=discord.TextStyle.paragraph, placeholder='Tell us everything we need to know', max_length=1000, required=False)
        self.add_item(self.subject); self.add_item(self.details)

    async def on_submit(self, i: discord.Interaction):
        await create_ticket(i, self.t, self.subject.value, self.details.value)

class CloseModal(discord.ui.Modal, title='Close ticket'):
    reason = discord.ui.TextInput(label='Reason', placeholder='Resolved / no response / duplicate…', max_length=200, required=False)

    async def on_submit(self, i: discord.Interaction):
        await close_ticket(i, self.reason.value or 'No reason given')

async def create_ticket(i: discord.Interaction, t, subject, details):
    g, s = i.guild, db.get_settings(i.guild.id)
    n_open = db.one("SELECT COUNT(*) c FROM tickets WHERE guild=? AND user=? AND status!='closed'", (str(g.id), str(i.user.id)))['c']
    if n_open >= int(s['ticketMax']):
        return await i.response.send_message(embed=embed('🎫 Ticket limit reached', f'You already have **{n_open}** open ticket(s). Your limit is **{s["ticketMax"]}**.'), ephemeral=True)
    await i.response.defer(ephemeral=True)
    num = db.one('SELECT COALESCE(MAX(num),0)+1 n FROM tickets WHERE guild=?', (str(g.id),))['n']
    cat = g.get_channel(int(s['ticketCategory'])) if s['ticketCategory'] else None
    role = g.get_role(int(s['supportRole'])) if s['supportRole'] else None
    P = discord.PermissionOverwrite
    ow = {g.default_role: P(view_channel=False),
          i.user: P(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
          g.me: P(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True)}
    if role: ow[role] = P(view_channel=True, send_messages=True, read_message_history=True, attach_files=True)
    try:
        ch = await g.create_text_channel(f"{slug(t['label'])}-{num:04d}", category=cat, topic=f'ticket:{i.user.id}:{num}', overwrites=ow)
    except discord.HTTPException:
        return await i.followup.send(embed=embed('⚠️ The gates are closed', 'I could not create the ticket channel. Please check my channel and role permissions.', RED), ephemeral=True)
    db.run('INSERT INTO tickets(guild,num,channel,user,category,subject,details,priority,status,created) VALUES(?,?,?,?,?,?,?,?,?,?)',
           (str(g.id), num, str(ch.id), str(i.user.id), t['label'], subject, details, 'normal', 'open', now()))
    e = embed(f"🎫 Ticket #{num:04d} — {t['label']}", s['ticketWelcome'].replace('{user}', i.user.mention).replace('{type}', t['label']))
    e.add_field(name='Subject', value=subject, inline=False)
    if details: e.add_field(name='Details', value=details[:1000], inline=False)
    e.add_field(name='Opened by', value=i.user.mention)
    e.add_field(name='Priority', value=PRI['normal'])
    e.add_field(name='Status', value='🟢 Open')
    ping = i.user.mention + (f' {role.mention}' if role and s['ticketPing'] else '')
    await ch.send(content=ping, embed=e, view=controls())
    await log(g, f"🎫 Ticket **#{num:04d}** ({t['label']}) opened by **{i.user}**")
    await i.followup.send(embed=embed('🎫 Your audience is ready', f'Your private ticket has been opened: {ch.mention}'), ephemeral=True)

async def claim(i: discord.Interaction):
    s, row = db.get_settings(i.guild.id), ticket_row(i.channel.id)
    if not row or row['status'] == 'closed': return await err(i, 'This is not an open ticket.')
    if not is_staff(i.user, s): return await err(i, 'Only staff can claim tickets.')
    if row['claimed_by']: return await err(i, f"Already claimed by <@{row['claimed_by']}>.")
    db.run("UPDATE tickets SET claimed_by=?, status='claimed' WHERE id=?", (str(i.user.id), row['id']))
    await i.response.send_message(embed=embed('🙋 Ticket claimed', f'{i.user.mention} will handle this ticket.'))
    try:
        e = i.message.embeds[0]
        for n, f in enumerate(e.fields):
            if f.name == 'Status': e.set_field_at(n, name='Status', value=f'🟡 Claimed by {i.user.mention}', inline=True)
        await i.message.edit(embed=e)
    except Exception: pass
    await log(i.guild, f"🙋 Ticket **#{row['num']:04d}** claimed by **{i.user}**")

async def build_transcript(ch):
    out = []
    async for m in ch.history(limit=None, oldest_first=True):
        text = m.content
        if not text and m.embeds: text = '[embed] ' + ' | '.join(filter(None, [m.embeds[0].title, m.embeds[0].description]))
        att = ' '.join(f'[file: {a.url}]' for a in m.attachments)
        out.append(f'[{m.created_at:%Y-%m-%d %H:%M}] {m.author} ({m.author.id}): {text} {att}'.strip())
    return '\n'.join(out)[:500000]

async def close_ticket(i: discord.Interaction, reason):
    g, s, row = i.guild, db.get_settings(i.guild.id), ticket_row(i.channel.id)
    if not row or row['status'] == 'closed': return await err(i, 'This is not an open ticket.')
    if str(i.user.id) != row['user'] and not is_staff(i.user, s): return await err(i, 'Only the ticket owner or staff can close this.')
    await i.response.send_message(embed=embed('🔒 Closing ticket', 'Saving the transcript… this channel will be deleted in a few seconds.'))
    ch, num = i.channel, row['num']
    transcript = await build_transcript(ch)
    db.run("UPDATE tickets SET status='closed', closed=?, closed_by=?, close_reason=?, transcript=? WHERE id=?", (now(), str(i.user.id), reason, transcript, row['id']))
    mins = max(1, (now() - row['created']) // 60000)
    summary = embed(f'📁 Ticket #{num:04d} closed', None, STEEL)
    for k, v in [('Opened by', f"<@{row['user']}>"), ('Category', row['category']), ('Priority', PRI.get(row['priority'], row['priority'])),
                 ('Claimed by', f"<@{row['claimed_by']}>" if row['claimed_by'] else 'Nobody'), ('Closed by', i.user.mention), ('Open for', f'{mins} min'), ('Reason', reason)]:
        summary.add_field(name=k, value=v)
    target = s['ticketLog'] or s['logChannel']
    lc = g.get_channel(int(target)) if target else None
    fname = f'ticket-{num:04d}.txt'
    if lc:
        try: await lc.send(embed=summary, file=discord.File(io.BytesIO(transcript.encode()), filename=fname))
        except discord.HTTPException: pass
    if s['ticketDM']:
        user = g.get_member(int(row['user']))
        if user:
            try:
                await user.send(embed=embed(f'🎫 Your ticket #{num:04d} in {g.name} was closed', f'**Reason:** {reason}\n\nHow was our service? Rate your experience below.'),
                                file=discord.File(io.BytesIO(transcript.encode()), filename=fname), view=rating_view(row['id']))
            except discord.HTTPException: pass
    await log(g, f"🔒 Ticket **#{num:04d}** closed by **{i.user}** — {reason}")
    await asyncio.sleep(5)
    try: await ch.delete()
    except discord.HTTPException: pass

class Tickets(commands.Cog):
    ticket = app_commands.Group(name='ticket', description='Ticket system', guild_only=True)

    def __init__(self, bot): self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, i: discord.Interaction):
        if i.type is not discord.InteractionType.component: return
        cid = (i.data or {}).get('custom_id', '')
        if not cid.startswith('tk:'): return
        p = cid.split(':')
        try:
            if p[1] == 'open' and i.guild:
                t = next((x for x in db.get_settings(i.guild.id)['ticketTypes'] if x['key'] == p[2]), None)
                if not t: return await i.response.send_message(embed=embed('📜 Category unavailable', 'That ticket category no longer exists. Please use the latest ticket panel.', RED), ephemeral=True)
                await i.response.send_modal(OpenModal(t))
            elif p[1] == 'claim' and i.guild: await claim(i)
            elif p[1] == 'close' and i.guild: await i.response.send_modal(CloseModal())
            elif p[1] == 'rate':
                row = db.one('SELECT * FROM tickets WHERE id=?', (int(p[2]),))
                if not row or row['user'] != str(i.user.id): return await i.response.send_message(embed=embed('🛡️ Access denied', 'This rating belongs to another knight.', RED), ephemeral=True)
                db.run('UPDATE tickets SET rating=? WHERE id=?', (int(p[3]), row['id']))
                await i.response.edit_message(content=None, embed=embed('⭐ Rating received', f'Thank you for rating this ticket {"⭐" * int(p[3])}.'), view=None)
        except Exception as e:
            print('Ticket interaction error:', repr(e))

    @ticket.command(name='panel', description='Post the ticket panel in this channel')
    @app_commands.default_permissions(manage_guild=True)
    async def panel(self, i: discord.Interaction):
        s = db.get_settings(i.guild.id)
        await i.channel.send(embed=embed(s['panelTitle'], s['panelDesc']), view=panel_view(s['ticketTypes']))
        await i.response.send_message(embed=embed('📜 Royal decree delivered', 'The ticket panel has been posted in this channel.'), ephemeral=True)

    @ticket.command(name='add', description='Add a user to this ticket')
    async def add(self, i: discord.Interaction, user: discord.Member):
        if not ticket_row(i.channel.id) or not is_staff(i.user, db.get_settings(i.guild.id)): return await err(i, 'Staff only, inside a ticket.')
        await i.channel.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
        await i.response.send_message(embed=embed('➕ User added', f'{user.mention} can now see this ticket.'))

    @ticket.command(name='remove', description='Remove a user from this ticket')
    async def remove(self, i: discord.Interaction, user: discord.Member):
        if not ticket_row(i.channel.id) or not is_staff(i.user, db.get_settings(i.guild.id)): return await err(i, 'Staff only, inside a ticket.')
        await i.channel.set_permissions(user, overwrite=None)
        await i.response.send_message(embed=embed('➖ User removed', f'{user.mention} was removed from this ticket.'))

    @ticket.command(name='priority', description="Set this ticket's priority")
    async def priority(self, i: discord.Interaction, level: Literal['low', 'normal', 'high', 'urgent']):
        row = ticket_row(i.channel.id)
        if not row or not is_staff(i.user, db.get_settings(i.guild.id)): return await err(i, 'Staff only, inside a ticket.')
        db.run('UPDATE tickets SET priority=? WHERE id=?', (level, row['id']))
        await i.response.send_message(embed=embed('🚩 Priority updated', f'Priority is now **{PRI[level]}**.'))
        await log(i.guild, f"🚩 Ticket **#{row['num']:04d}** priority set to {level} by **{i.user}**")

    @ticket.command(name='close', description='Close this ticket')
    async def close(self, i: discord.Interaction, reason: str = 'No reason given'):
        await close_ticket(i, reason)

async def setup(bot): await bot.add_cog(Tickets(bot))
