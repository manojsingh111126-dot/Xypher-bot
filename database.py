"""SQLite storage shared by the bot and the dashboard (both must run on the same host)."""
import sqlite3, json, os
from contextlib import closing

PATH = os.getenv('DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'xypher.db'))

DEFAULTS = {
    'welcomeChannel': None,
    'welcomeMsg': 'Hail, {user}! Welcome to **{server}**, brave knight. You are knight #{count}.',
    'logChannel': None, 'autorole': None, 'ticketCategory': None, 'supportRole': None,
    'ticketLog': None, 'ticketMax': 1, 'ticketPing': True, 'ticketDM': True,
    'ticketWelcome': 'Hello {user}! Thanks for opening a **{type}** ticket. Our guards will be with you shortly — please describe your issue in as much detail as you can.',
    'panelTitle': '🎫 Request an Audience',
    'panelDesc': 'Need help? Choose a category below to speak privately with the royal guard.',
    'ticketTypes': [
        {'key': 'support', 'label': 'Support', 'emoji': '🛡️', 'desc': 'General help'},
        {'key': 'report', 'label': 'Report', 'emoji': '⚔️', 'desc': 'Report a member or issue'},
        {'key': 'purchase', 'label': 'Purchase', 'emoji': '💰', 'desc': 'Billing and purchases'},
        {'key': 'other', 'label': 'Other', 'emoji': '📜', 'desc': 'Anything else'},
    ],
    'automod': {'links': False, 'spam': True, 'badwords': True, 'mentions': True, 'words': [], 'maxWarns': 3},
}

def _c():
    c = sqlite3.connect(PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c

def init():
    with closing(_c()) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS settings(guild TEXT PRIMARY KEY, data TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS users(guild TEXT, user TEXT, wallet INTEGER DEFAULT 0, bank INTEGER DEFAULT 0,
            daily REAL DEFAULT 0, work REAL DEFAULT 0, PRIMARY KEY(guild,user));
        CREATE TABLE IF NOT EXISTS warns(id INTEGER PRIMARY KEY AUTOINCREMENT, guild TEXT, user TEXT, mod TEXT, reason TEXT, ts INTEGER);
        CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT, guild TEXT, text TEXT, ts INTEGER);
        CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY AUTOINCREMENT, guild TEXT, num INTEGER, channel TEXT, user TEXT,
            category TEXT, subject TEXT, details TEXT, priority TEXT DEFAULT 'normal', status TEXT DEFAULT 'open', claimed_by TEXT,
            created INTEGER, closed INTEGER, closed_by TEXT, close_reason TEXT, rating INTEGER, transcript TEXT);
        CREATE INDEX IF NOT EXISTS idx_tickets_guild ON tickets(guild);
        CREATE TABLE IF NOT EXISTS sessions(sid TEXT PRIMARY KEY, data TEXT, exp REAL);
        ''')
        c.commit()

def run(sql, args=()):
    with closing(_c()) as c:
        c.execute(sql, args); c.commit()

def one(sql, args=()):
    with closing(_c()) as c:
        return c.execute(sql, args).fetchone()

def many(sql, args=()):
    with closing(_c()) as c:
        return c.execute(sql, args).fetchall()

def get_settings(gid):
    r = one('SELECT data FROM settings WHERE guild=?', (str(gid),))
    s = json.loads(r['data']) if r else {}
    return {**DEFAULTS, **s, 'automod': {**DEFAULTS['automod'], **s.get('automod', {})}}

def set_settings(gid, patch):
    cur = get_settings(gid)
    nxt = {**cur, **patch, 'automod': {**cur['automod'], **patch.get('automod', {})}}
    run('INSERT INTO settings(guild,data) VALUES(?,?) ON CONFLICT(guild) DO UPDATE SET data=excluded.data',
        (str(gid), json.dumps(nxt)))
    return nxt

def get_user(gid, uid):
    run('INSERT OR IGNORE INTO users(guild,user) VALUES(?,?)', (str(gid), str(uid)))
    return one('SELECT * FROM users WHERE guild=? AND user=?', (str(gid), str(uid)))

def add_coins(gid, uid, amount):
    get_user(gid, uid)
    run('UPDATE users SET wallet=wallet+? WHERE guild=? AND user=?', (amount, str(gid), str(uid)))

def add_warn(gid, uid, mod, reason):
    import time
    run('INSERT INTO warns(guild,user,mod,reason,ts) VALUES(?,?,?,?,?)', (str(gid), str(uid), str(mod), reason, int(time.time() * 1000)))
    return one('SELECT COUNT(*) c FROM warns WHERE guild=? AND user=?', (str(gid), str(uid)))['c']
