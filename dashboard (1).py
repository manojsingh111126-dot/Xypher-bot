"""Xypher Castle Command — pure-Python dashboard (NiceGUI) with Discord OAuth2 login.
Run:  python dashboard.py     (main.py starts it automatically when RUN_DASHBOARD=1)"""
import os, re, json, time, asyncio, secrets
from collections import Counter
from datetime import datetime, timedelta
from urllib.parse import urlencode, quote
from aiohttp import ClientSession
from dotenv import load_dotenv
from fastapi import Request
from fastapi.responses import RedirectResponse, PlainTextResponse
from nicegui import app, ui

load_dotenv()
import database as db

def _env(k, d=''): return (os.getenv(k) or d).strip().strip('"\'')
TOKEN, CLIENT_ID, CLIENT_SECRET = _env('DISCORD_TOKEN'), _env('CLIENT_ID'), _env('CLIENT_SECRET')
BASE_URL = _env('DASHBOARD_URL', 'http://localhost:8080')
if not BASE_URL.startswith('http'): BASE_URL = 'https://' + BASE_URL
BASE_URL = re.sub(r'/(auth/)?callback/?$', '', BASE_URL).rstrip('/')
REDIRECT = _env('REDIRECT_URI') or (BASE_URL + '/auth/callback')
print(f'🔐 OAuth redirect URI sent to Discord: {REDIRECT}  (client id: {CLIENT_ID or "MISSING"})')
API = 'https://discord.com/api/v10'
SECURE = BASE_URL.startswith('https')
PORT = int(os.getenv('SERVER_PORT') or os.getenv('PORT') or os.getenv('DASHBOARD_PORT') or 8080)
SESSION_DAYS = 7
PRI = {'low': '🟢 Low', 'normal': '🔵 Normal', 'high': '🟠 High', 'urgent': '🔴 Urgent'}
STATUS = {'open': '🟢 Open', 'claimed': '🟡 Claimed', 'closed': '🔒 Closed'}
db.init()

# ───────────────────────── Discord REST helpers ─────────────────────────
_http, _cache = None, {}

def http():
    global _http
    if _http is None or _http.closed: _http = ClientSession()
    return _http

async def cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and hit[0] > time.time(): return hit[1]
    val = await fn()
    _cache[key] = (time.time() + ttl, val)
    return val

async def dget(path, bearer=None):
    auth = f'Bearer {bearer}' if bearer else f'Bot {TOKEN}'
    for _ in range(3):
        async with http().get(API + path, headers={'Authorization': auth}) as r:
            if r.status == 429:
                await asyncio.sleep(min(5, float((await r.json()).get('retry_after', 1)))); continue
            r.raise_for_status()
            return await r.json()
    raise RuntimeError('Rate limited')

async def dpost(path, payload):
    async with http().post(API + path, json=payload, headers={'Authorization': f'Bot {TOKEN}'}) as r:
        return (r.status < 300), (await r.text())[:300]

async def bot_guilds():
    async def load():
        out, after = [], None
        for _ in range(10):
            page = await dget('/users/@me/guilds?limit=200' + (f'&after={after}' if after else ''))
            out += page
            if len(page) < 200: break
            after = page[-1]['id']
        return {g['id']: g for g in out}
    return await cached('bg', 30, load)

async def bot_user(): return await cached('bu', 3600, lambda: dget('/users/@me'))
async def get_channels(gid): return await cached(f'ch{gid}', 30, lambda: dget(f'/guilds/{gid}/channels'))
async def get_roles(gid): return await cached(f'ro{gid}', 30, lambda: dget(f'/guilds/{gid}/roles'))

async def uname(uid):
    try:
        u = await cached(f'u{uid}', 900, lambda: dget(f'/users/{uid}'))
        return u.get('global_name') or u.get('username') or str(uid)
    except Exception:
        return str(uid)

async def names(ids):
    ids = [i for i in set(ids) if i][:150]
    return dict(zip(ids, await asyncio.gather(*[uname(i) for i in ids])))

def avatar_url(u):
    if u.get('avatar'): return f"https://cdn.discordapp.com/avatars/{u['id']}/{u['avatar']}.png?size=128"
    return f"https://cdn.discordapp.com/embed/avatars/{(int(u['id']) >> 22) % 6}.png"

def sess(request: Request):
    sid = request.cookies.get('xy_sid')
    r = sid and db.one('SELECT data FROM sessions WHERE sid=? AND exp>?', (sid, time.time()))
    return json.loads(r['data']) if r else None

# ───────────────────────── OAuth2 routes ─────────────────────────
@app.get('/auth/debug')
async def auth_debug():
    return PlainTextResponse(f'redirect_uri = {REDIRECT}\nclient_id    = {CLIENT_ID or "MISSING"}\nsecret set   = {bool(CLIENT_SECRET)}\nbase url     = {BASE_URL}')

@app.get('/login')
async def login():
    if not (CLIENT_ID and CLIENT_SECRET): return PlainTextResponse('CLIENT_ID / CLIENT_SECRET are not configured.', status_code=500)
    state = secrets.token_urlsafe(16)
    url = 'https://discord.com/oauth2/authorize?' + urlencode({'client_id': CLIENT_ID, 'response_type': 'code', 'redirect_uri': REDIRECT,
                                                               'scope': 'identify guilds', 'state': state, 'prompt': 'none'})
    r = RedirectResponse(url)
    r.set_cookie('xy_state', state, max_age=600, httponly=True, secure=SECURE, samesite='lax')
    return r

@app.get('/auth/callback')
@app.get('/callback')
async def callback(request: Request):
    code, state = request.query_params.get('code'), request.query_params.get('state')
    if not code or not state or state != request.cookies.get('xy_state'): return RedirectResponse('/?error=login')
    try:
        async with http().post(API + '/oauth2/token', data={'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code',
                                                             'code': code, 'redirect_uri': REDIRECT}) as r:
            r.raise_for_status()
            tok = (await r.json())['access_token']
        user, guilds = await dget('/users/@me', tok), await dget('/users/@me/guilds', tok)
    except Exception:
        return RedirectResponse('/?error=login')
    managed = {g['id']: {'name': g['name'], 'icon': g.get('icon')} for g in guilds if g.get('owner') or int(g.get('permissions', 0)) & 0x28}
    data = {'user': {'id': user['id'], 'name': user.get('global_name') or user['username'], 'avatar': avatar_url(user)}, 'managed': managed}
    sid = secrets.token_urlsafe(32)
    db.run('DELETE FROM sessions WHERE exp<?', (time.time(),))
    db.run('INSERT INTO sessions(sid,data,exp) VALUES(?,?,?)', (sid, json.dumps(data), time.time() + SESSION_DAYS * 86400))
    resp = RedirectResponse('/')
    resp.set_cookie('xy_sid', sid, max_age=SESSION_DAYS * 86400, httponly=True, secure=SECURE, samesite='lax')
    resp.delete_cookie('xy_state')
    return resp

@app.get('/logout')
async def logout(request: Request):
    if sid := request.cookies.get('xy_sid'): db.run('DELETE FROM sessions WHERE sid=?', (sid,))
    resp = RedirectResponse('/')
    resp.delete_cookie('xy_sid')
    return resp

@app.get('/transcript/{gid}/{tid}')
async def transcript(request: Request, gid: str, tid: int):
    s = sess(request)
    if not s or gid not in s['managed']: return PlainTextResponse('Forbidden', status_code=403)
    r = db.one('SELECT num, transcript FROM tickets WHERE guild=? AND id=?', (gid, tid))
    if not r: return PlainTextResponse('Not found', status_code=404)
    return PlainTextResponse(r['transcript'] or 'No transcript saved yet.', headers={'Content-Disposition': f'attachment; filename="ticket-{r["num"]:04d}.txt"'})

# ───────────────────────── Theme ─────────────────────────
def castle_uri():
    p = ['<rect x="0" y="176" width="1200" height="44"/>'] + [f'<rect x="{x}" y="162" width="20" height="16"/>' for x in range(0, 1200, 36)]
    win = []
    for x, top, w in [(60, 112, 70), (260, 74, 86), (520, 34, 120), (800, 84, 84), (1040, 108, 78)]:
        p.append(f'<rect x="{x}" y="{top}" width="{w}" height="{220 - top}"/>')
        step = w / 5
        p += [f'<rect x="{x + k * step:.0f}" y="{top - 14}" width="{step * .6:.0f}" height="15"/>' for k in range(5)]
        p.append(f'<polygon points="{x + w / 2 - 18:.0f},{top - 14} {x + w / 2:.0f},{top - 58} {x + w / 2 + 18:.0f},{top - 14}"/>')
        win.append(f'<rect x="{x + w / 2 - 5:.0f}" y="{top + 24}" width="10" height="22" rx="5"/>')
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 220" preserveAspectRatio="xMidYMax slice">'
           f'<g fill="#07080b">{"".join(p)}</g><g fill="#c9a227" opacity=".55">{"".join(win)}</g></svg>')
    return 'data:image/svg+xml;utf8,' + quote(svg)

CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700;900&family=Alegreya+Sans:wght@400;500;700&display=swap');
html,body{background:#0e1014}
body,.q-field,.q-btn,.q-tab{font-family:'Alegreya Sans',sans-serif;font-size:16px}
body::before{content:"";position:fixed;inset:0;z-index:-2;
 background:radial-gradient(ellipse at 50% -10%,rgba(201,162,39,.18),transparent 55%),radial-gradient(circle at 12% 88%,rgba(166,61,52,.14),transparent 40%),
 linear-gradient(180deg,#0e1014,#171b22 60%,#1d222b)}
body::after{content:"";position:fixed;left:0;right:0;bottom:0;height:42vh;z-index:-1;pointer-events:none;opacity:.5;
 background:url("__CASTLE__") bottom center/cover no-repeat}
.q-layout,.q-page-container,.q-page{background:transparent!important}
.xy-brand{font-family:Cinzel,serif;font-weight:900;letter-spacing:.2em;color:#c9a227;font-size:21px}
.xy-h{font-family:Cinzel,serif;font-weight:700;color:#efe6cc;letter-spacing:.03em}
.xy-dim{color:#9aa1ab}
.xy-num{font-family:Cinzel,serif;font-size:28px;font-weight:700;color:#c9a227;line-height:1.1}
.xy-card{background:rgba(22,26,33,.88)!important;border:1px solid #3b434e;border-top:2px solid #8f7418;border-radius:6px!important;
 box-shadow:0 8px 28px rgba(0,0,0,.5)!important;backdrop-filter:blur(6px)}
.xy-header{background:rgba(12,14,18,.93)!important;border-bottom:1px solid #8f7418;backdrop-filter:blur(8px)}
.xy-drawer{background:rgba(15,17,22,.95)!important}
.q-btn.bg-primary{color:#1a1405!important;font-weight:700}
.q-tab{font-family:Cinzel,serif;letter-spacing:.04em}
.q-tab--active{color:#c9a227}
.xy-preview{background:#12151a;border:1px solid #3b434e;border-left:4px solid #c9a227;padding:12px 14px;border-radius:4px;white-space:pre-wrap}
.xy-transcript{background:#0f1217;border:1px solid #2f363f;border-radius:4px;padding:10px;font-family:monospace;font-size:13px}
.xy-gate{box-shadow:0 0 0 6px #0e1014,0 0 0 8px #4a525e,0 0 50px rgba(201,162,39,.25)!important;border:2px solid #8f7418!important}
.xy-crest{font-size:64px;line-height:1;filter:drop-shadow(0 0 14px rgba(201,162,39,.6));animation:pulse 3s ease-in-out infinite}
@keyframes pulse{50%{transform:scale(1.06)}}
.xy-loader{position:fixed;inset:0;z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;
 background:radial-gradient(ellipse at center,#232936 0%,#0c0e12 75%);transition:opacity .45s}
.xy-loader.out{opacity:0}
.xy-track{position:relative;width:min(440px,82vw);height:92px;overflow:hidden;border-bottom:3px solid #4a525e}
.xy-knight{position:absolute;bottom:0;font-size:68px;line-height:1;color:#c9a227;filter:drop-shadow(0 0 12px rgba(201,162,39,.55));
 animation:gallop 2.4s linear infinite,bob .32s ease-in-out infinite}
@keyframes gallop{from{left:-90px}to{left:100%}}
@keyframes bob{0%,100%{transform:scaleX(-1) translateY(0)}50%{transform:scaleX(-1) translateY(-9px) rotate(5deg)}}
.xy-sword{font-size:34px;animation:swing 1.2s ease-in-out infinite;transform-origin:50% 90%}
@keyframes swing{0%,100%{transform:rotate(-20deg)}50%{transform:rotate(20deg)}}
.xy-bar{width:min(320px,70vw);height:6px;background:#2a303a;border-radius:3px;overflow:hidden}
.xy-bar i{display:block;height:100%;width:40%;background:linear-gradient(90deg,transparent,#c9a227,transparent);animation:slide 1.3s ease-in-out infinite}
@keyframes slide{from{transform:translateX(-100%)}to{transform:translateX(260%)}}
.xy-msg{font-family:Cinzel,serif;letter-spacing:.22em;color:#c9a227;font-size:15px;text-transform:uppercase;text-align:center}
@media(prefers-reduced-motion:reduce){.xy-knight,.xy-sword,.xy-bar i,.xy-crest{animation:none}.xy-knight{left:45%}}
""".replace('__CASTLE__', castle_uri())

def theme():
    ui.add_css(CSS)
    ui.colors(primary='#c9a227', secondary='#7b8794', accent='#a63d34', positive='#5f9e6e', negative='#c0483d', info='#5b7ea6', warning='#d08a2e')
    ui.dark_mode(True)

def loader(msg='Rallying the knights…'):
    with ui.element('div').classes('xy-loader') as el:
        ui.label('🛡️').classes('xy-crest')
        with ui.element('div').classes('xy-track'):
            ui.label('♞\ufe0e').classes('xy-knight')
        with ui.row().classes('items-center gap-3'):
            ui.label('⚔️').classes('xy-sword')
            ui.label(msg).classes('xy-msg')
        with ui.element('div').classes('xy-bar'):
            ui.element('i')
    return el

async def hide(el):
    el.classes('out')
    await asyncio.sleep(.5)
    el.delete()

def title(text, icon=None, sub=None):
    with ui.row().classes('items-center gap-2 no-wrap'):
        if icon: ui.icon(icon).classes('text-primary text-2xl')
        ui.label(text).classes('xy-h text-xl')
    if sub: ui.label(sub).classes('xy-dim')

def stat(label, value, icon):
    with ui.card().classes('xy-card'):
        with ui.row().classes('items-center no-wrap gap-4'):
            ui.icon(icon).classes('text-4xl text-primary')
            with ui.column().classes('gap-0'):
                ui.label(str(value)).classes('xy-num')
                ui.label(label).classes('xy-dim')

def stat_grid(): return ui.grid(columns='repeat(auto-fit,minmax(210px,1fr))').classes('w-full')
def two_col(): return ui.grid(columns='repeat(auto-fit,minmax(280px,1fr))').classes('w-full')
def fmt(n): return f'{int(n):,}'
def tstr(ms): return datetime.fromtimestamp(ms / 1000).strftime('%Y-%m-%d %H:%M') if ms else '—'
def dur(sec):
    sec = int(sec)
    return f'{sec // 86400}d {sec % 86400 // 3600}h' if sec >= 86400 else f'{sec // 3600}h {sec % 3600 // 60}m' if sec >= 3600 else f'{max(1, sec // 60)}m'
def stars(n): return '★' * n + '☆' * (5 - n) if n else '—'

def shell(s, bg, current=None):
    with ui.header().classes('xy-header items-center justify-between q-px-md'):
        with ui.row().classes('items-center gap-3 no-wrap'):
            menu = ui.button(icon='menu').props('flat round dense color=primary').classes('lt-md')
            ui.label('🛡️').classes('text-2xl')
            ui.label('XYPHER').classes('xy-brand')
        with ui.row().classes('items-center gap-3 no-wrap'):
            ui.label(s['user']['name']).classes('gt-xs')
            with ui.avatar(size='36px'): ui.image(s['user']['avatar'])
            ui.button(icon='logout', on_click=lambda: ui.navigate.to('/logout')).props('flat round dense').tooltip('Log out')
    with ui.left_drawer(value=True, bordered=False).classes('xy-drawer q-pa-sm') as drawer:
        ui.button('Overview', icon='castle', on_click=lambda: ui.navigate.to('/')).props(f'flat no-caps align=left {"color=primary" if current is None else ""}').classes('w-full')
        ui.label('YOUR KINGDOMS').classes('xy-dim text-xs q-mt-md q-mb-xs q-ml-sm')
        for gid, g in s['managed'].items():
            if gid in bg:
                ui.button(g['name'], icon='shield', on_click=lambda gid=gid: ui.navigate.to(f'/guild/{gid}')).props(
                    f'flat no-caps align=left {"color=primary" if current == gid else ""}').classes('w-full ellipsis')
            else:
                ui.button(g['name'], icon='add_circle_outline', on_click=lambda gid=gid: ui.navigate.to(invite_url(gid), new_tab=True)).props('flat no-caps align=left color=grey').classes('w-full ellipsis').tooltip('Invite Xypher')
    menu.on('click', drawer.toggle)

def invite_url(gid):
    return 'https://discord.com/oauth2/authorize?' + urlencode({'client_id': CLIENT_ID, 'scope': 'bot applications.commands', 'permissions': 8, 'guild_id': gid, 'disable_guild_select': 'true'})

def opts(items, none='— None —'): return {'': none, **{i['id']: i['name'] for i in items}}
def select(label, items, value, none='— None —'): return ui.select(opts(items, none), label=label, value=value or '').props('outlined dense options-dense').classes('w-full')
def valid(v, items): return v if v and v in {i['id'] for i in items} else None

# ───────────────────────── Pages ─────────────────────────
@ui.page('/')
async def index(request: Request):
    theme()
    ld = loader('Opening the castle gates…')
    await ui.context.client.connected()
    s = sess(request)
    if not s:
        await hide(ld)
        with ui.column().classes('absolute-center items-center'):
            with ui.card().classes('xy-card xy-gate items-center text-center q-pa-xl').style('width:min(440px,92vw)'):
                ui.label('🛡️').classes('xy-crest')
                ui.label('XYPHER').classes('xy-brand text-4xl q-mt-sm')
                ui.label('CASTLE COMMAND').classes('xy-dim q-mb-md').style('letter-spacing:.3em')
                ui.label('Sign in with Discord to command your kingdoms — moderation, tickets, treasury and more.').classes('xy-dim q-mb-lg')
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('size=lg no-caps unelevated color=indigo-6').classes('w-full')
                if request.query_params.get('error'): ui.label('Login failed. Please try again.').classes('text-negative q-mt-md')
        return
    try: bg, bu = await bot_guilds(), await bot_user()
    except Exception: bg, bu = {}, {'username': 'Xypher'}
    await hide(ld)
    shell(s, bg)
    mine = [g for g in s['managed'] if g in bg]
    with ui.page_container():
        with ui.column().classes('w-full max-w-6xl mx-auto q-pa-md gap-4'):
            ui.label(f"Welcome back, Sir {s['user']['name']}").classes('xy-h text-3xl')
            ui.label('Choose a kingdom to manage, or invite Xypher to a new one.').classes('xy-dim')
            with stat_grid():
                stat('Kingdoms you command', len(mine), 'castle')
                stat('Kingdoms guarded', len(bg), 'shield')
                stat('Xycoins in circulation', fmt(db.one('SELECT COALESCE(SUM(wallet+bank),0) t FROM users')['t']), 'paid')
                stat('Open tickets', db.one("SELECT COUNT(*) c FROM tickets WHERE status!='closed'")['c'], 'confirmation_number')
            with two_col():
                for gid, g in s['managed'].items():
                    has = gid in bg
                    with ui.card().classes('xy-card'):
                        with ui.row().classes('items-center no-wrap gap-3'):
                            with ui.avatar(size='48px', color='grey-9'):
                                if g.get('icon'): ui.image(f"https://cdn.discordapp.com/icons/{gid}/{g['icon']}.png?size=64")
                                else: ui.label(g['name'][:1]).classes('xy-h')
                            with ui.column().classes('gap-0 grow').style('min-width:0'):
                                ui.label(g['name']).classes('xy-h ellipsis')
                                ui.label('Xypher is guarding this realm' if has else 'Xypher is not here yet').classes('xy-dim text-sm')
                        if has: ui.button('Manage', icon='tune', on_click=lambda gid=gid: ui.navigate.to(f'/guild/{gid}')).props('unelevated no-caps color=primary').classes('q-mt-md')
                        else: ui.button('Invite Xypher', icon='add', on_click=lambda gid=gid: ui.navigate.to(invite_url(gid), new_tab=True)).props('outline no-caps color=primary').classes('q-mt-md')

@ui.page('/guild/{gid}')
async def guild_page(request: Request, gid: str):
    theme()
    ld = loader('Summoning the council…')
    await ui.context.client.connected()
    s = sess(request)
    if not s: return ui.navigate.to('/')
    try:
        bg = await bot_guilds()
        if gid not in s['managed'] or gid not in bg: raise PermissionError('You cannot manage that kingdom, or Xypher is not in it.')
        chans, roles = await get_channels(gid), await get_roles(gid)
    except Exception as e:
        await hide(ld); shell(s, {})
        with ui.page_container(), ui.card().classes('xy-card q-ma-lg'): ui.label(f'⚠️ {e}')
        return
    st = db.get_settings(gid)
    tickets = [dict(r) for r in db.many('SELECT id,num,user,category,subject,priority,status,claimed_by,created,closed,closed_by,rating FROM tickets WHERE guild=? ORDER BY id DESC', (gid,))]
    richest = [dict(r) for r in db.many('SELECT user,wallet,bank FROM users WHERE guild=? ORDER BY wallet+bank DESC LIMIT 10', (gid,))]
    warns = [dict(r) for r in db.many('SELECT user,reason,ts FROM warns WHERE guild=? ORDER BY id DESC LIMIT 20', (gid,))]
    logs = [dict(r) for r in db.many('SELECT text,ts FROM logs WHERE guild=? ORDER BY id DESC LIMIT 30', (gid,))]
    nm = await names([t['user'] for t in tickets[:150]] + [t['claimed_by'] for t in tickets[:150]] + [r['user'] for r in richest] + [w['user'] for w in warns])
    N = lambda uid: nm.get(uid, uid or '—') if uid else '—'
    text_ch = [{'id': c['id'], 'name': '#' + c['name']} for c in chans if c['type'] in (0, 5)]
    cat_ch = [{'id': c['id'], 'name': c['name']} for c in chans if c['type'] == 4]
    role_l = [{'id': r['id'], 'name': r['name']} for r in roles if r['id'] != gid and not r.get('managed')]
    gname = s['managed'][gid]['name']
    await hide(ld)
    shell(s, bg, gid)

    def save(patch, msg='Saved to the scrolls ✔'):
        db.set_settings(gid, patch); ui.notify(msg, type='positive')

    with ui.page_container():
        with ui.column().classes('w-full max-w-6xl mx-auto q-pa-md gap-3'):
            ui.label(gname).classes('xy-h text-3xl')
            with ui.tabs().props('align=left inline-label mobile-arrows').classes('w-full') as tabs:
                t_over = ui.tab('Overview', icon='castle')
                t_wel = ui.tab('Welcome', icon='waving_hand')
                t_auto = ui.tab('Automod', icon='gavel')
                t_tick = ui.tab('Tickets', icon='confirmation_number')
                t_eco = ui.tab('Xycoins', icon='paid')
                t_led = ui.tab('Ledger', icon='menu_book')
            with ui.tab_panels(tabs, value=t_tick if request.query_params.get('tab') == 'tickets' else t_over).classes('w-full bg-transparent'):

                # ── Overview
                with ui.tab_panel(t_over).classes('q-pa-none'), ui.column().classes('w-full gap-4'):
                    n_open = sum(1 for t in tickets if t['status'] != 'closed')
                    with stat_grid():
                        stat('Open tickets', n_open, 'confirmation_number')
                        stat('Total tickets', len(tickets), 'inventory_2')
                        stat('Warnings issued', db.one('SELECT COUNT(*) c FROM warns WHERE guild=?', (gid,))['c'], 'warning')
                        stat('Xycoins here', fmt(db.one('SELECT COALESCE(SUM(wallet+bank),0) t FROM users WHERE guild=?', (gid,))['t']), 'paid')
                    with two_col():
                        with ui.card().classes('xy-card'):
                            title('Royal checklist', 'checklist')
                            for label, v in [('Welcome channel', st['welcomeChannel']), ('Mod-log channel', st['logChannel']), ('Autorole', st['autorole']),
                                             ('Ticket category', st['ticketCategory']), ('Support role', st['supportRole'])]:
                                with ui.row().classes('items-center gap-2'):
                                    ui.icon('check_circle' if v else 'radio_button_unchecked').classes('text-positive' if v else 'xy-dim')
                                    ui.label(label)
                        with ui.card().classes('xy-card'):
                            title('Recent events', 'history')
                            for l in logs[:6]: ui.label(f"{tstr(l['ts'])} — {l['text'].replace('**', '')}").classes('text-sm')
                            if not logs: ui.label('Nothing recorded yet.').classes('xy-dim')

                # ── Welcome
                with ui.tab_panel(t_wel).classes('q-pa-none'), ui.card().classes('xy-card w-full gap-3'):
                    title('Welcome & Autorole', 'waving_hand', 'Greet new knights and give them a role automatically.')
                    with two_col():
                        wc = select('Welcome channel', text_ch, st['welcomeChannel'])
                        ar = select('Role for new members', role_l, st['autorole'])
                    wm = ui.textarea('Welcome message', value=st['welcomeMsg']).props('outlined autogrow').classes('w-full')
                    ui.label('Placeholders: {user}  {server}  {count}').classes('xy-dim text-sm')
                    pv = ui.label().classes('xy-preview w-full')
                    def upd(*_): pv.text = (wm.value or '').replace('{user}', '@NewKnight').replace('{server}', gname).replace('{count}', '42').replace('**', '')
                    wm.on_value_change(upd); upd()
                    ui.button('Save welcome settings', icon='save', on_click=lambda: save({'welcomeChannel': valid(wc.value, text_ch), 'autorole': valid(ar.value, role_l), 'welcomeMsg': (wm.value or '')[:1500]})).props('unelevated no-caps color=primary')

                # ── Automod
                with ui.tab_panel(t_auto).classes('q-pa-none'), ui.card().classes('xy-card w-full gap-2'):
                    a = st['automod']
                    title('Automod', 'gavel', 'Automatic protection for your realm.')
                    sw = {}
                    for k, (n, d) in {'links': ('Block links', 'Deletes messages containing links or invites'), 'spam': ('Block spam', '6+ messages within 5 seconds'),
                                      'badwords': ('Block banned words', 'Uses the word list below'), 'mentions': ('Block mass mentions', '5+ users mentioned in one message')}.items():
                        with ui.row().classes('w-full items-center justify-between no-wrap'):
                            with ui.column().classes('gap-0'): ui.label(n); ui.label(d).classes('xy-dim text-sm')
                            sw[k] = ui.switch(value=a[k])
                    mw = ui.number('Warnings before a 10-minute timeout', value=a['maxWarns'], min=1, max=20, format='%.0f').props('outlined dense').classes('w-64')
                    words = ui.select(list(a['words']), value=list(a['words']), label='Banned words (type and press Enter)', multiple=True, with_input=True,
                                      new_value_mode='add-unique').props('outlined use-chips').classes('w-full')
                    ui.button('Save automod settings', icon='save', on_click=lambda: save({'automod': {**{k: bool(v.value) for k, v in sw.items()},
                        'maxWarns': int(mw.value or 3), 'words': [w.lower().strip() for w in (words.value or []) if w.strip()][:200]}})).props('unelevated no-caps color=primary')

                # ── Tickets
                with ui.tab_panel(t_tick).classes('q-pa-none'):
                    build_tickets(gid, st, tickets, N, text_ch, cat_ch, role_l, save)

                # ── Xycoins
                with ui.tab_panel(t_eco).classes('q-pa-none'), ui.card().classes('xy-card w-full'):
                    title('Hall of Fortune', 'emoji_events', 'The richest knights in this realm.')
                    if richest:
                        ui.table(columns=[{'name': 'r', 'label': 'Rank', 'field': 'r', 'align': 'left'}, {'name': 'n', 'label': 'Knight', 'field': 'n', 'align': 'left'},
                                          {'name': 'w', 'label': 'Wallet', 'field': 'w', 'align': 'right'}, {'name': 'b', 'label': 'Bank', 'field': 'b', 'align': 'right'},
                                          {'name': 't', 'label': 'Net worth', 'field': 't', 'align': 'right'}],
                                 rows=[{'r': ['🥇', '🥈', '🥉'][i] if i < 3 else i + 1, 'n': N(x['user']), 'w': fmt(x['wallet']), 'b': fmt(x['bank']), 't': f"🪙 {fmt(x['wallet'] + x['bank'])}"} for i, x in enumerate(richest)],
                                 row_key='r').classes('w-full bg-transparent').props('flat dense')
                    else: ui.label('No fortunes yet. Knights earn Xycoins with /daily and /work.').classes('xy-dim')

                # ── Ledger
                with ui.tab_panel(t_led).classes('q-pa-none'), two_col():
                    with ui.card().classes('xy-card'):
                        title('Royal ledger', 'menu_book')
                        for l in logs:
                            with ui.row().classes('w-full justify-between no-wrap'):
                                ui.label(l['text'].replace('**', '')).classes('text-sm'); ui.label(tstr(l['ts'])).classes('xy-dim text-xs')
                        if not logs: ui.label('Nothing recorded yet.').classes('xy-dim')
                    with ui.card().classes('xy-card'):
                        title('Recent warnings', 'warning')
                        for w in warns:
                            with ui.row().classes('w-full justify-between no-wrap'):
                                ui.label(f"{N(w['user'])} — {w['reason']}").classes('text-sm'); ui.label(tstr(w['ts'])).classes('xy-dim text-xs')
                        if not warns: ui.label('A peaceful realm.').classes('xy-dim')

# ───────────────────────── Ticket center ─────────────────────────
def build_tickets(gid, st, tickets, N, text_ch, cat_ch, role_l, save):
    with ui.column().classes('w-full gap-3'):
        with ui.tabs().props('dense align=left inline-label').classes('w-full') as sub:
            s_dash = ui.tab('Insights', icon='insights')
            s_list = ui.tab('All tickets', icon='list_alt')
            s_set = ui.tab('Settings', icon='tune')
            s_pan = ui.tab('Panel', icon='dashboard_customize')
        with ui.tab_panels(sub, value=s_dash).classes('w-full bg-transparent'):

            # Insights
            with ui.tab_panel(s_dash).classes('q-pa-none'), ui.column().classes('w-full gap-4'):
                closed = [t for t in tickets if t['status'] == 'closed']
                rated = [t['rating'] for t in tickets if t['rating']]
                res = [(t['closed'] - t['created']) / 1000 for t in closed if t['closed']]
                with stat_grid():
                    stat('Total tickets', len(tickets), 'inventory_2')
                    stat('Open', sum(t['status'] == 'open' for t in tickets), 'mark_email_unread')
                    stat('Claimed', sum(t['status'] == 'claimed' for t in tickets), 'support_agent')
                    stat('Closed', len(closed), 'task_alt')
                    stat('Avg rating', f'{sum(rated) / len(rated):.1f} ★' if rated else '—', 'star')
                    stat('Avg resolution', dur(sum(res) / len(res)) if res else '—', 'timer')
                days = [(datetime.now() - timedelta(days=d)).date() for d in range(13, -1, -1)]
                per = Counter(datetime.fromtimestamp(t['created'] / 1000).date() for t in tickets)
                with two_col():
                    with ui.card().classes('xy-card'):
                        title('Tickets — last 14 days', 'bar_chart')
                        ui.echart({'backgroundColor': 'transparent', 'grid': {'left': 30, 'right': 8, 'top': 16, 'bottom': 24}, 'tooltip': {'trigger': 'axis'},
                                   'xAxis': {'type': 'category', 'data': [d.strftime('%d %b') for d in days], 'axisLabel': {'color': '#9aa1ab'}},
                                   'yAxis': {'type': 'value', 'minInterval': 1, 'axisLabel': {'color': '#9aa1ab'}, 'splitLine': {'lineStyle': {'color': '#2f363f'}}},
                                   'series': [{'type': 'bar', 'data': [per.get(d, 0) for d in days], 'itemStyle': {'color': '#c9a227'}}]}).classes('w-full').style('height:220px')
                    with ui.card().classes('xy-card gap-2'):
                        title('By category', 'category')
                        cats = Counter(t['category'] for t in tickets)
                        for c, n in cats.most_common(6):
                            with ui.row().classes('w-full justify-between'): ui.label(c); ui.label(str(n)).classes('xy-dim')
                            ui.linear_progress(value=n / max(cats.values()), show_value=False).props('color=primary rounded')
                        if not cats: ui.label('No tickets yet.').classes('xy-dim')
                        title('Top guards (claims)', 'military_tech')
                        for u, n in Counter(t['claimed_by'] for t in tickets if t['claimed_by']).most_common(5):
                            with ui.row().classes('w-full justify-between'): ui.label(N(u)); ui.label(f'{n} claimed').classes('xy-dim')

            # All tickets
            with ui.tab_panel(s_list).classes('q-pa-none'), ui.card().classes('xy-card w-full gap-2'):
                def rows(flt='All'):
                    return [{'id': t['id'], 'num': f"#{t['num']:04d}", 'user': N(t['user']), 'category': t['category'], 'subject': t['subject'][:60],
                             'priority': PRI.get(t['priority'], t['priority']), 'status': STATUS.get(t['status'], t['status']), 'claimed': N(t['claimed_by']),
                             'created': tstr(t['created']), 'rating': stars(t['rating'] or 0)} for t in tickets if flt == 'All' or t['status'] == flt.lower()]
                with ui.row().classes('w-full items-center justify-between'):
                    title('All tickets', 'list_alt')
                    flt = ui.toggle(['All', 'Open', 'Claimed', 'Closed'], value='All').props('unelevated no-caps')
                    search = ui.input(placeholder='Search tickets…').props('outlined dense clearable').classes('w-64')
                cols = [{'name': k, 'label': l, 'field': k, 'sortable': True, 'align': 'left'} for k, l in
                        [('num', '#'), ('user', 'Opened by'), ('category', 'Category'), ('subject', 'Subject'), ('priority', 'Priority'),
                         ('status', 'Status'), ('claimed', 'Claimed by'), ('created', 'Created'), ('rating', 'Rating')]]
                table = ui.table(columns=cols, rows=rows(), row_key='id', pagination=10).classes('w-full bg-transparent cursor-pointer').props('flat dense')
                search.bind_value_to(table, 'filter')
                def refilter(e=None): table.rows = rows(flt.value); table.update()
                flt.on_value_change(refilter)
                table.on('rowClick', lambda e: detail(gid, e.args[1]['id'], N))
                ui.label('Click a ticket to see its details and full transcript.').classes('xy-dim text-sm')

            # Settings
            with ui.tab_panel(s_set).classes('q-pa-none'), ui.card().classes('xy-card w-full gap-3'):
                title('Ticket settings', 'tune', 'How tickets behave in this kingdom.')
                with two_col():
                    tc = select('Ticket category (where channels are created)', cat_ch, st['ticketCategory'])
                    sr = select('Support role (can see & claim tickets)', role_l, st['supportRole'])
                    tl = select('Transcript / ticket-log channel', text_ch, st['ticketLog'], '— Use mod-log channel —')
                    tm = ui.number('Max open tickets per user', value=st['ticketMax'], min=1, max=10, format='%.0f').props('outlined dense').classes('w-full')
                with ui.row().classes('gap-6'):
                    tp = ui.switch('Ping support role on new tickets', value=st['ticketPing'])
                    td = ui.switch('DM transcript & rating request to the user', value=st['ticketDM'])
                tw = ui.textarea('Ticket welcome message — {user} {type}', value=st['ticketWelcome']).props('outlined autogrow').classes('w-full')
                ui.button('Save ticket settings', icon='save', on_click=lambda: save({'ticketCategory': valid(tc.value, cat_ch), 'supportRole': valid(sr.value, role_l),
                    'ticketLog': valid(tl.value, text_ch), 'ticketMax': int(tm.value or 1), 'ticketPing': bool(tp.value), 'ticketDM': bool(td.value),
                    'ticketWelcome': (tw.value or '')[:1500]})).props('unelevated no-caps color=primary')

            # Panel
            with ui.tab_panel(s_pan).classes('q-pa-none'), ui.card().classes('xy-card w-full gap-3'):
                title('Ticket panel', 'dashboard_customize', 'Design the panel and deploy it to any channel — no commands needed.')
                pt = ui.input('Panel title', value=st['panelTitle']).props('outlined dense').classes('w-full')
                pd = ui.textarea('Panel description', value=st['panelDesc']).props('outlined autogrow').classes('w-full')
                types = [{'key': t.get('key') or secrets.token_hex(3), 'label': t['label'], 'emoji': t.get('emoji', ''), 'desc': t.get('desc', '')} for t in st['ticketTypes']]
                ui.label('Ticket categories (max 5 — each becomes a button)').classes('xy-dim')
                @ui.refreshable
                def editor():
                    for idx, t in enumerate(types):
                        with ui.row().classes('w-full items-center no-wrap gap-2'):
                            ui.input('Emoji').props('outlined dense').classes('w-24').bind_value(t, 'emoji')
                            ui.input('Label').props('outlined dense').classes('w-48').bind_value(t, 'label')
                            ui.input('Description').props('outlined dense').classes('grow').bind_value(t, 'desc')
                            ui.button(icon='delete', on_click=lambda idx=idx: (types.pop(idx), editor.refresh())).props('flat round color=negative')
                    if len(types) < 5:
                        ui.button('Add category', icon='add', on_click=lambda: (types.append({'key': secrets.token_hex(3), 'label': 'New', 'emoji': '🎫', 'desc': ''}), editor.refresh())).props('outline no-caps color=primary')
                editor()
                dest = select('Deploy to channel', text_ch, '', '— Choose a channel —')
                def collect():
                    clean = [{**t, 'label': (t['label'] or 'Ticket').strip()[:80]} for t in types if (t['label'] or '').strip()][:5]
                    return {'panelTitle': (pt.value or 'Tickets')[:256], 'panelDesc': (pd.value or '')[:2000], 'ticketTypes': clean}
                async def deploy():
                    patch, ch = collect(), valid(dest.value, text_ch)
                    if not ch: return ui.notify('Choose a channel first.', type='warning')
                    if not patch['ticketTypes']: return ui.notify('Add at least one category.', type='warning')
                    db.set_settings(gid, patch)
                    comps = [{'type': 2, 'style': 1, 'label': t['label'], 'custom_id': f"tk:open:{t['key']}", **({'emoji': {'name': t['emoji']}} if t.get('emoji') else {})} for t in patch['ticketTypes']]
                    ok, info = await dpost(f'/channels/{ch}/messages', {'embeds': [{'title': patch['panelTitle'], 'description': patch['panelDesc'], 'color': 0xC9A227,
                                           'footer': {'text': 'Xypher • Knight of the Realm ⚔️'}}], 'components': [{'type': 1, 'components': comps}]})
                    ui.notify('Panel deployed! ⚔️' if ok else f'Discord refused: {info}', type='positive' if ok else 'negative')
                with ui.row().classes('gap-2'):
                    ui.button('Save panel', icon='save', on_click=lambda: save(collect())).props('unelevated no-caps color=primary')
                    ui.button('Deploy panel', icon='rocket_launch', on_click=deploy).props('outline no-caps color=primary')

def detail(gid, tid, N):
    r = db.one('SELECT * FROM tickets WHERE guild=? AND id=?', (gid, tid))
    if not r: return ui.notify('Ticket not found', type='negative')
    with ui.dialog().on('hide', lambda: None) as d, ui.card().classes('xy-card gap-2').style('width:min(780px,95vw);max-width:95vw'):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label(f"Ticket #{r['num']:04d} — {r['category']}").classes('xy-h text-xl')
            ui.badge(STATUS.get(r['status'], r['status'])).props('color=primary text-color=dark')
        ui.label(r['subject']).classes('text-lg')
        if r['details']: ui.label(r['details']).classes('xy-preview w-full')
        with ui.grid(columns='repeat(auto-fit,minmax(200px,1fr))').classes('w-full gap-2'):
            for k, v in [('Opened by', N(r['user'])), ('Priority', PRI.get(r['priority'], r['priority'])), ('Claimed by', N(r['claimed_by'])), ('Created', tstr(r['created'])),
                         ('Closed', tstr(r['closed'])), ('Closed by', N(r['closed_by'])), ('Reason', r['close_reason'] or '—'), ('Rating', stars(r['rating'] or 0))]:
                with ui.column().classes('gap-0'): ui.label(k).classes('xy-dim text-xs'); ui.label(str(v))
        ui.separator()
        ui.label('Transcript').classes('xy-h')
        with ui.scroll_area().classes('xy-transcript w-full').style('height:260px'):
            ui.label(r['transcript'] or 'No transcript yet — it is saved when the ticket is closed.').classes('whitespace-pre-wrap')
        with ui.row().classes('justify-end w-full'):
            ui.button('Download transcript', icon='download', on_click=lambda: ui.download(f'/transcript/{gid}/{tid}')).props('outline no-caps color=primary')
            ui.button('Close', on_click=d.close).props('flat no-caps')
    d.open()

if __name__ in {'__main__', '__mp_main__'}:
    ui.run(host='0.0.0.0', port=PORT, title='Xypher — Castle Command', favicon='🛡️', dark=True, reload=False, show=False,
           storage_secret=CLIENT_SECRET or 'xypher-storage', uvicorn_logging_level='warning')
