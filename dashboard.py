"""Xypher web dashboard (single file). Put this next to bot.py, then in bot.py: await self.load_extension("dashboard")
Env needed: CLIENT_SECRET, REDIRECT_URI (optional DASHBOARD_PORT). Edits your cogs' live settings."""
import os, sys, json, time, hashlib, secrets, base64, aiohttp, discord
from urllib.parse import urlencode
from aiohttp import web
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional
import random

_TF = "dashboard_data.json"   # message templates are stored here (next to your other .json files)
def _tload():
    try:
        with open(_TF, encoding="utf8") as f: return json.load(f)
    except (FileNotFoundError, ValueError): return {}
def _tsave(d):
    with open(_TF, "w", encoding="utf8") as f: json.dump(d, f, indent=1)

# ================= settings <-> your cogs =================
from theme import safe_dm
from automod import MODULES   # your automod.py

def F(key, label, type, hint="", path=None, group="", **kw):
    return dict(key=key, label=label, type=type, hint=hint, group=group, path=tuple(path or (key,)), **kw)

def _it(id, name, **kw):
    return {"id": id, "name": name, "title": "", "author": "", "desc": "", "fields": [], "footer": "", "thumb": False, "color": "#c9a227", **kw}
INV_TPLS = [
    _it("classic", "Classic", desc="{user} joined the server\nInvited by {inviter}\nTotal invites: **{invites}**"),
    _it("card", "Card", author="New member joined", desc="**{user}** was invited by **{inviter}**\nInvite code: `{code}`", footer="Member #{count}", thumb=True),
    _it("detailed", "Detailed", title="\U0001F4E5 Member joined", fields=[["Member", "{user}"], ["Invited by", "{inviter}"], ["Invites", "{invites}"]], footer="Code {code} | {count} members", thumb=True),
    _it("minimal", "Minimal", color="#2b2d31", desc="\u2795 {user} joined, invited by {inviter} ({invites} invites)"),
]

SECTIONS = [
 dict(id="automod", title="AutoMod", cog="AutoMod",
      container=lambda cog, g: cog.cfg(g.id), save=lambda cog, g: cog.save(),
      fields=[F("m_" + k, v, "bool", path=("modules", k), group="Rules") for k, v in MODULES.items()] + [
        F("spam_messages", "Spam: messages allowed", "number", path=("spam", "messages"), min=2, max=20, group="Limits"),
        F("spam_seconds", "Spam: window (seconds)", "number", path=("spam", "seconds"), min=1, max=60, group="Limits"),
        F("dup_count", "Duplicates: same message count", "number", path=("duplicates", "count"), min=2, max=10, group="Limits"),
        F("dup_seconds", "Duplicates: window (seconds)", "number", path=("duplicates", "seconds"), min=5, max=300, group="Limits"),
        F("caps_percent", "Caps: % that triggers", "number", path=("caps", "percent"), min=30, max=100, group="Limits"),
        F("caps_min", "Caps: minimum letters", "number", path=("caps", "min_length"), min=5, max=100, group="Limits"),
        F("mention_limit", "Max mentions per message", "number", path=("mentions", "limit"), min=2, max=30, group="Limits"),
        F("emoji_limit", "Max emojis per message", "number", path=("emojis", "limit"), min=3, max=50, group="Limits"),
        F("badwords", "Bad words", "lines", "One per line. Use * as a wildcard", path=("badwords",), group="Lists"),
        F("allowed_domains", "Allowed link domains", "lines", "One per line, like youtube.com", path=("allowed_domains",), group="Lists"),
        F("ignored_channels", "Ignored channels", "multichannel", path=("ignored_channels",), group="Exceptions"),
        F("ignored_roles", "Ignored roles", "multirole", path=("ignored_roles",), group="Exceptions"),
        F("ignore_staff", "Ignore staff (Admin / Manage Messages)", "bool", path=("ignore_staff",), group="Exceptions"),
        F("pun_action", "Punishment", "select", "After enough strikes", path=("punishment", "action"), group="Punishment",
          options=[["none", "None (delete + warn)"], ["timeout", "Timeout"], ["kick", "Kick"], ["ban", "Ban"]]),
        F("pun_strikes", "Strikes before punishment", "number", path=("punishment", "strikes"), min=1, max=20, group="Punishment"),
        F("pun_window", "Strike window (seconds)", "number", path=("punishment", "window"), min=30, max=3600, group="Punishment"),
        F("pun_duration", "Timeout length (seconds)", "number", path=("punishment", "duration"), min=60, max=2419200, group="Punishment")]),

 dict(id="welcome", title="Welcome", cog="Welcome",
      container=lambda cog, g: cog.cfg(g.id), save=lambda cog, g: cog.save(),
      fields=[
        F("welcome_enabled", "Send welcome messages", "bool", group="Join"),
        F("welcome_channel", "Welcome channel", "channel", group="Join"),
        F("welcome_dm", "Also DM the welcome message to new members", "bool", group="Join"),
        F("welcome_text", "Text above the embed", "text", "The only part that can ping the new member", max=500, group="Join"),
        F("welcome_title", "Embed title", "text", max=200, group="Join"),
        F("welcome_message", "Embed message", "area", "{user} {name} {server} {count} {line}", max=1800, group="Join"),
        F("welcome_footer", "Footer", "text", "Blank = Xypher default, __off__ = no footer", nullable=True, max=200, group="Join"),
        F("welcome_color", "Embed color", "color", group="Look"),
        F("thumbnail_mode", "Thumbnail", "select", path=("thumbnail_mode",), group="Look",
          options=[["avatar", "Member avatar"], ["server", "Server icon"], ["custom", "Custom URL"], ["none", "None"]]),
        F("thumbnail_url", "Custom thumbnail URL", "text", "https:// link", nullable=True, https=True, group="Look"),
        F("image_url", "Big image URL", "text", "https:// link", nullable=True, https=True, group="Look")]),

 dict(id="leave", title="Leave messages", cog="Welcome",
      container=lambda cog, g: cog.cfg(g.id), save=lambda cog, g: cog.save(),
      fields=[
        F("goodbye_enabled", "Send goodbye messages", "bool"),
        F("goodbye_channel", "Goodbye channel", "channel", "Where the message is posted when someone leaves"),
        F("goodbye_message", "Goodbye message", "area", "You can use {name} {server} {count}", max=1800)]),

 dict(id="joinroles", title="Join roles", cog="Welcome",
      container=lambda cog, g: cog.cfg(g.id), save=lambda cog, g: cog.save(),
      fields=[
        F("auto_roles_enabled", "Give roles to new members", "bool", group="Roles"),
        F("auto_roles", "Roles given on join", "multirole", "Every new member gets these automatically", group="Roles"),
        F("verify_role", "Verified role", "role", "Given to members who press the verify button", group="Checks"),
        F("min_age_days", "Minimum account age (days)", "number", "Accounts younger than this are turned away. 0 turns it off", min=0, max=365, group="Checks")]),

 dict(id="invites", title="Invite tracker", cog="InviteTracker",
      container=lambda cog, g: cog.cfg(g.id), save=lambda cog, g: cog.save(),
      fields=[
        F("enabled", "Track invites", "bool", "Needs the Manage Server permission so I can see invite uses"),
        F("channel", "Invite log channel", "channel", "Every new member is announced here"),
        F("template", "Message design", "invtpl", "Pick how the message looks", options=INV_TPLS)]),

 dict(id="leveling", title="Leveling", cog="Leveling",
      container=lambda cog, g: cog.guild(g.id)["config"], save=lambda cog, g: (_fix_xp(cog, g), cog.save()),
      fields=[
        F("enabled", "Enable leveling", "bool"),
        F("multiplier", "XP multiplier", "number", min=0.1, max=10, float=True),
        F("xp_min", "XP per message (min)", "number", min=1, max=1000),
        F("xp_max", "XP per message (max)", "number", min=1, max=1000),
        F("cooldown", "Seconds between XP messages", "number", min=0, max=3600),
        F("voice_xp", "Voice XP per minute (0 = off)", "number", min=0, max=1000),
        F("announce", "Announce level-ups", "bool"),
        F("announce_channel", "Level-up channel", "channel", "Blank = same channel as the message"),
        F("stack_rewards", "Keep old reward roles", "bool"),
        F("ignored_channels", "No-XP channels", "multichannel"),
        F("rewards", "Role rewards", "lines", "One per line: level=Role name  (example: 5=Regular)",
          get=lambda cog, g: [f"{l}={g.get_role(r).name}" for l, r in sorted(cog.guild(g.id)["rewards"].items(), key=lambda kv: int(kv[0])) if g.get_role(r)],
          set=lambda cog, g, v: _set_rewards(cog, g, v))]),

 dict(id="moderation", title="Moderation", cog="Moderation",
      container=lambda cog, g: cog.store.guild(g.id), save=lambda cog, g: cog.store.save(),
      fields=[F("log_channel", "Mod log channel", "channel", "Every mod action is logged here as a case")]),

 dict(id="tickets", title="Tickets", cog="Tickets",
      container=lambda cog, g: cog.cfg(g.id), save=lambda cog, g: cog.save(),
      fields=[
        F("category", "Ticket category", "category", "New tickets are created inside it"),
        F("support_roles", "Support roles", "multirole"),
        F("log_channel", "Ticket log channel", "channel"),
        F("max_open", "Max open tickets per member", "number", min=1, max=10)]),

 dict(id="utility", title="Suggestions", cog="Utility",
      container=lambda cog, g: {}, save=lambda cog, g: cog.store.save(),
      fields=[F("suggest_channel", "Suggestions channel", "channel", "Where /suggest posts go",
                get=lambda cog, g: cog.store.data["suggest_channel"].get(str(g.id)),
                set=lambda cog, g, v: cog.store.data["suggest_channel"].pop(str(g.id), None) if v is None else cog.store.data["suggest_channel"].__setitem__(str(g.id), v))]),
]

def _fix_xp(cog, g):
    c = cog.guild(g.id)["config"]
    if c["xp_min"] > c["xp_max"]: c["xp_min"], c["xp_max"] = c["xp_max"], c["xp_min"]

def _set_rewards(cog, g, lines):
    out = {}
    for line in lines:
        lvl, _, name = line.partition("=")
        role = next((r for r in g.roles if r.name.lower() == name.strip().lower()), None)
        if not lvl.strip().isdigit() or not role: raise ValueError(f"Bad reward line: {line}")
        out[str(int(lvl))] = role.id
    cog.guild(g.id)["rewards"] = out

# ---------- type conversion ----------
def to_ui(f, v):
    t = f["type"]
    if t in ("channel", "role", "category"): return str(v) if v else ""
    if t in ("multichannel", "multirole"): return [str(x) for x in (v or [])]
    if t == "lines": return list(v or []) if isinstance(v, list) else []
    if t == "color": return "#%06x" % (v or 0)
    if t == "bool": return bool(v)
    return "" if v is None else v

def from_ui(f, v, g):
    t = f["type"]
    if t in ("channel", "role", "category"):
        if not v: return None
        i = int(v); ok = (g.get_role(i) if t == "role" else g.get_channel(i))
        if not ok: raise ValueError(f"{f['label']}: not found in this server")
        return i
    if t in ("multichannel", "multirole"):
        ids = [int(x) for x in v]
        if any(not (g.get_role(i) if t == "multirole" else g.get_channel(i)) for i in ids): raise ValueError(f"{f['label']}: not found in this server")
        return ids
    if t == "lines": return [str(x).strip() for x in v if str(x).strip()][:200]
    if t == "color": return int(str(v).lstrip("#"), 16) if len(str(v).lstrip("#")) == 6 else 0
    if t == "bool": return bool(v)
    if t == "number":
        n = float(v) if f.get("float") else int(v)
        return max(f["min"], min(f["max"], n))
    if t == "invtpl":
        if v not in [o["id"] for o in f["options"]]: raise ValueError("Pick one of the designs")
        return v
    if t == "select":
        if v not in [o[0] for o in f["options"]]: raise ValueError(f"{f['label']}: invalid choice")
        return v
    s = str(v).strip()
    if f.get("max") and len(s) > f["max"]: raise ValueError(f"{f['label']}: too long")
    if f.get("https") and s and not (s.startswith("https://") and " " not in s): raise ValueError(f"{f['label']}: must be an https:// link")
    return (s or None) if f.get("nullable") else s

def read(sec, cog, g):
    box, out = sec["container"](cog, g), {}
    for f in sec["fields"]:
        if "get" in f: v = f["get"](cog, g)
        else:
            v = box
            for p in f["path"]: v = v[p]
        out[f["key"]] = to_ui(f, v)
    return out

def write(sec, cog, g, values):
    box = sec["container"](cog, g)
    for f in sec["fields"]:
        if f["key"] not in values: continue
        v = from_ui(f, values[f["key"]], g)
        if "set" in f: f["set"](cog, g, v)
        else:
            d = box
            for p in f["path"][:-1]: d = d[p]
            d[f["path"][-1]] = v
    sec["save"](cog, g)

def schema():
    return [dict(id=s["id"], title=s["title"], fields=[{k: v for k, v in f.items() if k not in ("get", "set", "path")} for f in s["fields"]]) for s in SECTIONS]

M = sys.modules[__name__]

# ================= web server + Discord login =================

API = "https://discord.com/api/v10"
SESSIONS: dict = {}
_SF = "dashboard_sessions.json"   # remembered logins (only a hash of each cookie is stored, never the cookie itself)
_hash = lambda sid: hashlib.sha256(sid.encode()).hexdigest()
def _sload():
    try:
        with open(_SF, encoding="utf8") as f: d = json.load(f)
        SESSIONS.update({k: v for k, v in d.items() if v.get("exp", 0) > time.time()})
    except (FileNotFoundError, ValueError, AttributeError): pass
def _spersist():
    keep = {k: v for k, v in SESSIONS.items() if v.get("remember") and v.get("user") and v.get("exp", 0) > time.time()}
    with open(_SF, "w", encoding="utf8") as f: json.dump(keep, f)
_sload()
SEC = {s["id"]: s for s in M.SECTIONS}

def can_manage(g):
    p = int(g["permissions"]); return bool(g.get("owner") or p & 0x8 or p & 0x20)

@web.middleware
async def session_mw(request, handler):
    sid = request.cookies.get("sid"); key = _hash(sid) if sid else None
    if not key or key not in SESSIONS or SESSIONS[key].get("exp", time.time() + 1) < time.time():
        if len(SESSIONS) > 2000:
            for k in [k for k, v in SESSIONS.items() if not v.get("user")]: SESSIONS.pop(k, None)
        sid = secrets.token_hex(24); key = _hash(sid); SESSIONS[key] = {}
    request["s"], request["k"] = SESSIONS[key], key
    resp = await handler(request)
    resp.set_cookie("sid", sid, httponly=True, samesite="Lax", secure=(os.getenv("REDIRECT_URI") or "").startswith("https"),
                    max_age=30 * 86400 if request["s"].get("remember") else None)
    return resp

OWN: set = set()
async def load_owners(bot):
    ids = {int(x) for x in (os.getenv("OWNER_ID") or "").replace(",", " ").split() if x.isdigit()}
    if not ids:
        try:
            info = await bot.application_info()
            ids = {m.id for m in info.team.members} if info.team else {info.owner.id}
        except Exception: ids = set()
    OWN.clear(); OWN.update(ids)
    print(f"[dashboard] owner access for {len(ids)} account(s)" if ids else "[dashboard] no owner found: set OWNER_ID to control every server")

def build(bot) -> web.Application:
    SECRET, REDIRECT, J = os.getenv("CLIENT_SECRET"), os.getenv("REDIRECT_URI"), web.json_response
    async def dreq(method, path, **kw):
        async with aiohttp.ClientSession() as s, s.request(method, API + path, **kw) as r:
            if r.status >= 400: raise RuntimeError(r.status)
            return await r.json()
    def deny(request, gid=None):
        if not request["s"].get("user"): return J({"error": "Not logged in"}, status=401)
        own = int(request["s"]["user"]["id"]) in OWN
        if gid and ((gid not in request["s"]["guilds"] and not own) or not bot.get_guild(int(gid))):
            return J({"error": "You cannot manage this server, or Xypher is not in it"}, status=403)
        if gid and not own:   # live check, so a remembered login stops working the moment someone loses their permissions
            g = bot.get_guild(int(gid)); m = g.get_member(int(request["s"]["user"]["id"]))
            if m and not (g.owner_id == m.id or m.guild_permissions.administrator or m.guild_permissions.manage_guild):
                return J({"error": "You no longer have permission to manage this server"}, status=403)

    async def login(request):
        request["s"]["state"] = secrets.token_hex(16); request["s"]["remember"] = request.query.get("remember") == "1"
        return web.HTTPFound("https://discord.com/oauth2/authorize?" + urlencode({"client_id": bot.user.id, "redirect_uri": REDIRECT,
            "response_type": "code", "scope": "identify guilds", "state": request["s"]["state"]}))
    async def callback(request):
        s = request["s"]
        try:
            if not request.query.get("code") or request.query.get("state") != s.get("state"): return web.HTTPFound("/?error=state")
            tok = await dreq("POST", "/oauth2/token", data={"client_id": bot.user.id, "client_secret": SECRET, "grant_type": "authorization_code",
                                                            "code": request.query["code"], "redirect_uri": REDIRECT})
            h = {"Authorization": f"Bearer {tok['access_token']}"}
            s["user"] = await dreq("GET", "/users/@me", headers=h)
            gl = [g for g in await dreq("GET", "/users/@me/guilds", headers=h) if can_manage(g)]
            s["guild_list"], s["guilds"] = gl, [g["id"] for g in gl]
            s["exp"] = time.time() + (30 if s.get("remember") else 1) * 86400
            if s.get("remember"): _spersist()
            return web.HTTPFound("/")
        except Exception: return web.HTTPFound("/?error=login")
    async def logout(request):
        request["s"].clear(); SESSIONS.pop(request["k"], None); _spersist(); return web.HTTPFound("/")
    async def config(request): return J({"clientId": str(bot.user.id)})
    async def me(request):
        u = request["s"].get("user"); return J({"user": u, "owner": bool(u and int(u["id"]) in OWN)})
    async def schema(request): return deny(request) or J(M.schema())
    async def guilds(request):
        e = deny(request)
        if e: return e
        out = [{"id": g["id"], "name": g["name"], "icon": g.get("icon"), "botIn": bot.get_guild(int(g["id"])) is not None, "members": getattr(bot.get_guild(int(g["id"])), "member_count", 0)} for g in request["s"]["guild_list"]]
        if int(request["s"]["user"]["id"]) in OWN:   # the bot owner sees every server the bot is in
            have = {x["id"] for x in out}
            out += [{"id": str(g.id), "name": g.name, "icon": g.icon.key if g.icon else None, "botIn": True, "members": g.member_count, "viaOwner": True} for g in bot.guilds if str(g.id) not in have]
        return J(out)

    async def guild_get(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e
        g, data = bot.get_guild(int(gid)), {}
        for sec in M.SECTIONS:
            cog = bot.get_cog(sec["cog"])
            if cog: data[sec["id"]] = M.read(sec, cog, g)
        return J({"values": data,
            "channels": [{"id": str(c.id), "name": c.name} for c in g.text_channels],
            "categories": [{"id": str(c.id), "name": c.name} for c in g.categories],
            "roles": [{"id": str(r.id), "name": r.name} for r in g.roles if not r.is_default() and not r.managed]})

    async def section_put(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e
        sec = SEC.get(request.match_info["sec"]); g = bot.get_guild(int(gid))
        cog = bot.get_cog(sec["cog"]) if sec else None
        if not cog: return J({"error": "Unknown section, or its module isn't loaded"}, status=404)
        try: M.write(sec, cog, g, await request.json())
        except (ValueError, TypeError, KeyError) as ex: return J({"error": str(ex) or "Invalid value"}, status=400)
        return J({"ok": True})

    def _name(g, uid):
        m = g.get_member(int(uid)); return m.display_name if m else f"User {uid}"

    async def overview(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e
        g = bot.get_guild(int(gid)); n = lambda u: _name(g, u)
        A, W, L, T, Mo = (bot.get_cog(x) for x in ("AutoMod", "Welcome", "Leveling", "Tickets", "Moderation"))
        out = {"stats": {"members": g.member_count, "channels": len(g.channels), "roles": len(g.roles), "latency": round(bot.latency * 1000)}, "status": []}
        if A: c = A.cfg(g.id); k = sum(1 for v in c["modules"].values() if v); out["status"].append(["AutoMod", f"{k} of {len(c['modules'])} rules on", k > 0, "automod"])
        if W: c = W.cfg(g.id); ok = bool(c.get("welcome_enabled", True) and c["welcome_channel"]); out["status"].append(["Welcome", "Welcoming new members" if ok else "Off or no channel set", ok, "welcome"])
        if L: ok = bool(L.guild(g.id)["config"]["enabled"]); out["status"].append(["Leveling", "Members earn XP" if ok else "Off", ok, "leveling"])
        if Mo: ok = bool(Mo.store.guild(g.id)["log_channel"]); out["status"].append(["Moderation log", "Logging every action" if ok else "No log channel set", ok, "moderation"])
        if T: ok = bool(T.cfg(g.id)["category"]); out["status"].append(["Tickets", "Ready" if ok else "Not set up", ok, "tickets"])
        I = bot.get_cog("InviteTracker")
        if I: c = I.cfg(g.id); ok = bool(c["enabled"] and c["channel"]); out["status"].append(["Invite tracker", "Posting invite messages" if ok else "Off or no channel set", ok, "invites"])
        if L:
            from leveling import level_info
            out["leaderboard"] = [{"name": n(u), "xp": d["xp"], "level": level_info(d["xp"])[0], "messages": d.get("messages", 0)} for u, d in L.ranking(g.id)[:10]]
        if Mo: out["cases"] = [{"id": c["id"], "type": c["type"], "user": n(c["user"]), "mod": n(c["mod"]), "reason": str(c["reason"])[:140], "time": c["time"]} for c in Mo.store.guild(g.id)["cases"][-25:][::-1]]
        if T:
            out["tickets"] = [{"number": x["number"], "subject": x["subject"], "opener": n(x["opener"]), "claimed": n(x["claimed_by"]) if x["claimed_by"] else "", "created": x["created"]}
                              for x in T.data["tickets"].values() if x["guild"] == g.id]
        return J(out)

    async def announce(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e
        g, b = bot.get_guild(int(gid)), await request.json()
        ch, msg = g.get_channel(int(b.get("channel") or 0)), str(b.get("message", "")).strip()[:3500]
        if not ch or not msg: return J({"error": "Pick a channel and write a message."}, status=400)
        from theme import knight_embed
        try: await ch.send(embed=knight_embed(str(b.get("title", "")).strip()[:200] or "Announcement", msg))
        except Exception: return J({"error": "I can't post in that channel. Check my permissions there."}, status=400)
        return J({"ok": True})

    STY = ("primary", "secondary", "success", "danger")
    def clean_panel(g, d, old):
        t = lambda v, n: str(v or "").strip()[:n]
        def rid(v, role=False):
            if not v: return None
            i = int(v)
            if not (g.get_role(i) if role else g.get_channel(i)): raise ValueError("Something you picked is not in this server")
            return i
        cat = rid(d.get("category"))
        if cat and not isinstance(g.get_channel(cat), discord.CategoryChannel): raise ValueError("Ticket category must be a category")
        col = t(d.get("embed_color"), 7)
        out = {"name": t(d.get("name"), 60) or "Panel", "embed_title": t(d.get("embed_title"), 200) or "Need Help?", "embed_description": t(d.get("embed_description"), 2000),
               "embed_color": col if len(col) == 7 and col[0] == "#" else "#c9a227", "max_open": max(1, min(10, int(d.get("max_open") or 1))), "ticket_message": t(d.get("ticket_message"), 1500), "buttons": []}
        if cat: out["category"] = cat
        if (lg := rid(d.get("log_channel"))): out["log_channel"] = lg
        if (roles := [rid(x, True) for x in d.get("support_roles", [])]): out["support_roles"] = roles
        for b in (d.get("buttons") or [])[:25]:
            qs = [{"label": t(q.get("label"), 45), "style": "paragraph" if q.get("style") == "paragraph" else "short", "required": bool(q.get("required", True)),
                   "placeholder": t(q.get("placeholder"), 100), "max_length": max(1, min(4000, int(q.get("max_length") or 100)))} for q in (b.get("questions") or [])[:5] if t(q.get("label"), 45)]
            out["buttons"].append({"label": t(b.get("label"), 80) or "Open Ticket", "emoji": t(b.get("emoji"), 32), "style": b.get("style") if b.get("style") in STY else "primary",
                                   "form_enabled": bool(b.get("form_enabled", True)), "form_title": t(b.get("form_title"), 45), "questions": qs,
                                   "ticket_subject": t(b.get("ticket_subject"), 100), "ticket_message": t(b.get("ticket_message"), 1500)})
        if not out["buttons"]: raise ValueError("Add at least one button")
        out["button_label"] = out["buttons"][0]["label"]
        for k in ("channel", "message_id"):
            if old.get(k): out[k] = old[k]
        return out

    def panel_ui(pid, p):
        btn = {"label": "Open Ticket", "emoji": "", "style": "primary", "form_enabled": True, "form_title": "Open a ticket", "questions": [], "ticket_subject": "", "ticket_message": ""}
        return {"id": pid, "name": p.get("name") or p.get("embed_title") or "Panel", "embed_title": p.get("embed_title", "Need Help?"), "embed_description": p.get("embed_description", ""),
                "embed_color": p.get("embed_color", "#c9a227"), "category": str(p.get("category") or ""), "support_roles": [str(x) for x in p.get("support_roles", [])],
                "log_channel": str(p.get("log_channel") or ""), "max_open": p.get("max_open", 1), "ticket_message": p.get("ticket_message", ""),
                "channel": str(p.get("channel") or ""), "message_id": str(p.get("message_id") or ""), "buttons": [{**btn, **b} for b in p.get("buttons") or [btn]]}

    def panel_msg(pid, p):
        from theme import knight_embed
        from tickets import TicketPanel
        return knight_embed(p["embed_title"], p["embed_description"], int(p["embed_color"].lstrip("#"), 16)), TicketPanel(p["button_label"], pid, p)

    def tick(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e, None, None
        T = bot.get_cog("Tickets")
        return (None, bot.get_guild(int(gid)), T) if T else (J({"error": "The Tickets module is not loaded"}, status=404), None, None)

    async def refresh(g, pid, p):
        try: ch = g.get_channel(int(p["channel"])); msg = await ch.fetch_message(int(p["message_id"])); e, v = panel_msg(pid, p); await msg.edit(embed=e, view=v)
        except Exception: pass

    async def panels_get(request):
        e, g, T = tick(request)
        return e or J([panel_ui(k, v) for k, v in T.cfg(g.id)["panels"].items()])

    async def panel_put(request):
        e, g, T = tick(request)
        if e: return e
        P, pid = T.cfg(g.id)["panels"], request.match_info["pid"]
        try: data = clean_panel(g, await request.json(), P.get(pid, {}))
        except (ValueError, TypeError, AttributeError) as ex: return J({"error": str(ex) or "Invalid panel"}, status=400)
        if pid not in P: pid = "p" + secrets.token_hex(3)
        P[pid] = data; T.save()
        if data.get("message_id"): await refresh(g, pid, data)
        return J({"id": pid})

    async def panel_delete(request):
        e, g, T = tick(request)
        if e: return e
        P = T.cfg(g.id)["panels"]; p = P.pop(request.match_info["pid"], None); T.save()
        if p and p.get("message_id"):
            try: await (await g.get_channel(int(p["channel"])).fetch_message(int(p["message_id"]))).delete()
            except Exception: pass
        return J({"ok": True})

    async def panel_post(request):
        e, g, T = tick(request)
        if e: return e
        pid = request.match_info["pid"]; p = T.cfg(g.id)["panels"].get(pid); ch = g.get_channel(int((await request.json()).get("channel") or 0))
        if not p or not ch: return J({"error": "Save the panel and pick a channel first"}, status=400)
        try:
            emb, view = panel_msg(pid, p); msg = None
            if p.get("message_id") and p.get("channel") == ch.id:
                try: msg = await ch.fetch_message(int(p["message_id"])); await msg.edit(embed=emb, view=view)
                except discord.NotFound: msg = None
            if msg is None: msg = await ch.send(embed=emb, view=view)
        except discord.HTTPException: return J({"error": "I can't post in that channel. Check my permissions there."}, status=400)
        p["channel"], p["message_id"] = ch.id, msg.id; T.save()
        return J({"ok": True})

    async def cases_get(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e
        Mo, g = bot.get_cog("Moderation"), bot.get_guild(int(gid))
        if not Mo: return J({"error": "The Moderation module is not loaded"}, status=404)
        return J([{"id": c["id"], "type": c["type"], "user": _name(g, c["user"]), "user_id": str(c["user"]), "mod": _name(g, c["mod"]), "reason": str(c["reason"])[:500],
                   "time": c["time"], "active": bool(c.get("active"))} for c in Mo.store.guild(g.id)["cases"][::-1][:300]])

    def case_of(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e, None, None
        Mo = bot.get_cog("Moderation")
        if not Mo: return J({"error": "The Moderation module is not loaded"}, status=404), None, None
        c = next((x for x in Mo.store.guild(int(gid))["cases"] if str(x["id"]) == request.match_info["cid"]), None)
        return (None, Mo, (int(gid), c)) if c else (J({"error": "Case not found"}, status=404), None, None)

    async def case_put(request):
        e, Mo, gc = case_of(request)
        if e: return e
        gc[1]["reason"] = str((await request.json()).get("reason", "")).strip()[:500] or "No reason provided"; Mo.store.save()
        return J({"ok": True})

    async def case_delete(request):
        e, Mo, gc = case_of(request)
        if e: return e
        Mo.store.guild(gc[0])["cases"].remove(gc[1]); Mo.store.save()
        return J({"ok": True})

    def clean_tpl(d, old):
        t = lambda v, n: str(v or "").strip()[:n]
        def url(v):
            v = t(v, 500)
            if v and not v.startswith("https://"): raise ValueError("Links must start with https://")
            return v
        out = {"name": t(d.get("name"), 60) or "Template", "content": t(d.get("content"), 2000), "embeds": [], "buttons": []}
        for e in (d.get("embeds") or [])[:3]:
            col = t(e.get("color"), 7)
            out["embeds"].append({"title": t(e.get("title"), 256), "description": t(e.get("description"), 4000), "color": col if len(col) == 7 and col[0] == "#" else "#c9a227",
                                  "author": t(e.get("author"), 256), "footer": t(e.get("footer"), 2048), "image": url(e.get("image")), "thumbnail": url(e.get("thumbnail")),
                                  "fields": [{"name": t(f.get("name"), 256), "value": t(f.get("value"), 1024), "inline": bool(f.get("inline"))} for f in (e.get("fields") or [])[:10]
                                             if t(f.get("name"), 256) and t(f.get("value"), 1024)]})
        for b in (d.get("buttons") or [])[:5]:
            if t(b.get("label"), 80) and url(b.get("url")): out["buttons"].append({"label": t(b.get("label"), 80), "url": url(b.get("url")), "emoji": t(b.get("emoji"), 32)})
        if not out["content"] and not any(x["title"] or x["description"] or x["image"] or x["fields"] for x in out["embeds"]): raise ValueError("Add some text or an embed first")
        for k in ("channel", "message_id"):
            if old.get(k): out[k] = old[k]
        return out

    def tpl_msg(tp):
        embeds = []
        for x in tp["embeds"]:
            em = discord.Embed(title=x["title"] or None, description=x["description"] or None, color=int(x["color"].lstrip("#"), 16))
            if x["author"]: em.set_author(name=x["author"])
            if x["footer"]: em.set_footer(text=x["footer"])
            if x["image"]: em.set_image(url=x["image"])
            if x["thumbnail"]: em.set_thumbnail(url=x["thumbnail"])
            for f in x["fields"]: em.add_field(name=f["name"], value=f["value"], inline=f["inline"])
            embeds.append(em)
        view = discord.ui.View(timeout=None)
        for b in tp["buttons"]: view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label=b["label"], url=b["url"], emoji=b["emoji"] or None))
        return tp["content"] or None, embeds, view

    async def tpl_get(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e
        return J([{**v, "id": k} for k, v in _tload().get(gid, {}).items()])

    async def tpl_put(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e
        d = _tload(); T = d.setdefault(gid, {}); tid = request.match_info["tid"]
        try: data = clean_tpl(await request.json(), T.get(tid, {}))
        except (ValueError, TypeError, AttributeError) as ex: return J({"error": str(ex) or "Invalid template"}, status=400)
        if tid not in T: tid = "t" + secrets.token_hex(3)
        T[tid] = data; _tsave(d)
        if data.get("message_id"):
            try:
                ch = bot.get_guild(int(gid)).get_channel(int(data["channel"])); msg = await ch.fetch_message(int(data["message_id"])); c, em, v = tpl_msg(data)
                await msg.edit(content=c, embeds=em, view=v if data["buttons"] else None)
            except Exception: pass
        return J({"id": tid})

    async def tpl_delete(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e
        d = _tload(); d.get(gid, {}).pop(request.match_info["tid"], None); _tsave(d)
        return J({"ok": True})

    async def tpl_send(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e
        g = bot.get_guild(int(gid)); d = _tload(); tp = d.get(gid, {}).get(request.match_info["tid"]); ch = g.get_channel(int((await request.json()).get("channel") or 0))
        if not tp or not ch: return J({"error": "Save the template and pick a channel first"}, status=400)
        try:
            c, em, v = tpl_msg(tp); msg = None
            if tp.get("message_id") and tp.get("channel") == ch.id:
                try: msg = await ch.fetch_message(int(tp["message_id"])); await msg.edit(content=c, embeds=em, view=v if tp["buttons"] else None)
                except discord.NotFound: msg = None
            if msg is None: msg = await ch.send(content=c, embeds=em, **({"view": v} if tp["buttons"] else {}))
        except discord.HTTPException: return J({"error": "Discord rejected the message. Check the emoji, links and my permissions in that channel."}, status=400)
        tp["channel"], tp["message_id"] = ch.id, msg.id; _tsave(d)
        return J({"ok": True})

    def gwc(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e, None, None
        cog = bot.get_cog("Giveaways")
        return (None, bot.get_guild(int(gid)), cog) if cog else (J({"error": "The giveaway module is not loaded"}, status=404), None, None)

    async def gw_list(request):
        e, g, cog = gwc(request)
        if e: return e
        out = []
        for k, d in cog.g(g.id).items():
            ch = g.get_channel(int(d["channel"]))
            out.append({"id": k, "prize": d["prize"], "status": d["status"], "end": d["end"], "winners": d["winners"], "entries": len(d["entries"]),
                        "channel": ch.name if ch else "deleted-channel", "winner_names": [_name(g, u) for u in d.get("winners_ids", [])]})
        return J(sorted([x for x in out if x["status"] == "active"], key=lambda x: x["end"]) + sorted([x for x in out if x["status"] != "active"], key=lambda x: -x["end"])[:30])

    async def gw_start(request):
        e, g, cog = gwc(request)
        if e: return e
        try:
            b = await request.json(); prize = str(b.get("prize", "")).strip()[:200]
            mult = {"minutes": 60, "hours": 3600, "days": 86400}.get(b.get("unit")); secs = int(float(b.get("dur") or 0) * mult) if mult else 0
            ch = g.get_channel(int(b.get("channel") or 0)); role = int(b["role"]) if b.get("role") else None
        except (ValueError, TypeError, AttributeError): return J({"error": "Something in the form is not valid"}, status=400)
        if not prize: return J({"error": "Write the prize first"}, status=400)
        if not 60 <= secs <= 30 * 86400: return J({"error": "Pick a duration between 1 minute and 30 days"}, status=400)
        if not isinstance(ch, discord.TextChannel): return J({"error": "Choose a text channel"}, status=400)
        if role and not g.get_role(role): return J({"error": "That role is not in this server"}, status=400)
        try: k = await cog.start(g, ch, int(request["s"]["user"]["id"]), prize, str(b.get("description", "")).strip()[:1000], max(1, min(20, int(b.get("winners") or 1))), secs, role)
        except discord.HTTPException: return J({"error": "I can't post in that channel. Check my permissions there."}, status=400)
        return J({"id": k})

    async def gw_act(request):
        e, g, cog = gwc(request)
        if e: return e
        d, act = cog.g(g.id).get(request.match_info["gid"]), request.match_info["act"]
        if not d: return J({"error": "Giveaway not found"}, status=404)
        if act == "end" and d["status"] == "active": await cog.finish(g.id, d["id"])
        elif act == "reroll" and d["status"] != "active": await cog.finish(g.id, d["id"], reroll=True)
        else: return J({"error": "That action doesn't apply to this giveaway"}, status=400)
        return J({"ok": True})

    async def gw_del(request):
        e, g, cog = gwc(request)
        if e: return e
        d = cog.g(g.id).pop(request.match_info["gid"], None); cog.save()
        if d and d["status"] == "active":
            try: await (await g.get_channel(int(d["channel"])).fetch_message(int(d["message_id"]))).delete()
            except Exception: pass
        return J({"ok": True})

    async def inviters(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e
        cog, g = bot.get_cog("InviteTracker"), bot.get_guild(int(gid))
        if not cog: return J({"error": "The invite tracker module is not loaded"}, status=404)
        rows = sorted(((int(u), c) for u, c in cog.guild(g.id)["counts"].items() if c["total"]), key=lambda r: -(r[1]["total"] - r[1]["left"]))[:10]
        return J([{"name": _name(g, u), "invites": c["total"] - c["left"], "total": c["total"], "left": c["left"]} for u, c in rows])

    def rrc(request):
        gid = request.match_info["id"]
        if (e := deny(request, gid)): return e, None, None
        cog = bot.get_cog("ReactionRoles")
        return (None, bot.get_guild(int(gid)), cog) if cog else (J({"error": "The reaction roles module is not loaded"}, status=404), None, None)

    def clean_rr(g, d, old, uid):
        t = lambda v, n: str(v or "").strip()[:n]
        mode = d.get("mode") if d.get("mode") in ("buttons", "dropdown", "reactions") else "buttons"
        col, host = t(d.get("color"), 7), g.get_member(uid)
        strong = host and (g.owner_id == host.id or host.guild_permissions.administrator)
        out = {"name": t(d.get("name"), 60) or "Roles", "mode": mode, "title": t(d.get("title"), 200) or "Pick your roles", "description": t(d.get("description"), 2000),
               "color": col if len(col) == 7 and col[0] == "#" else "#c9a227", "unique": bool(d.get("unique")), "items": []}
        for x in (d.get("items") or [])[:20 if mode == "reactions" else 25]:
            role = g.get_role(int(x.get("role") or 0))
            if not role: raise ValueError("Choose a role for every row")
            if role.managed or role.is_default(): raise ValueError(f"{role.name} can't be given out")
            if role >= g.me.top_role: raise ValueError(f"I can't give {role.name} because it is above my highest role. Move my role higher first")
            if host and not strong and not (host.guild_permissions.manage_roles and role < host.top_role): raise ValueError(f"You can't hand out {role.name}. It is above your highest role")
            emoji, label = t(x.get("emoji"), 64), t(x.get("label"), 80)
            if mode == "reactions" and not emoji: raise ValueError("Every row needs an emoji in reactions mode")
            if (mode == "dropdown" or not emoji) and not label: label = role.name[:80]
            out["items"].append({"emoji": emoji, "label": label, "role": role.id, "description": t(x.get("description"), 100)})
        if not out["items"]: raise ValueError("Add at least one role")
        if mode == "reactions" and len({i["emoji"] for i in out["items"]}) < len(out["items"]): raise ValueError("Each role needs a different emoji")
        for k in ("channel", "message_id"):
            if old.get(k): out[k] = old[k]
        return out

    async def rr_list(request):
        e, g, cog = rrc(request)
        return e or J([{**v, "id": k, "role_ids": [str(i["role"]) for i in v["items"]], "channel": str(v.get("channel") or ""), "message_id": str(v.get("message_id") or ""),
                        "items": [{**i, "role": str(i["role"])} for i in v["items"]]} for k, v in cog.g(g.id).items()])

    async def rr_put(request):
        e, g, cog = rrc(request)
        if e: return e
        P, pid = cog.g(g.id), request.match_info["pid"]
        try: data = clean_rr(g, await request.json(), P.get(pid, {}), int(request["s"]["user"]["id"]))
        except (ValueError, TypeError, AttributeError) as ex: return J({"error": str(ex) or "Invalid panel"}, status=400)
        if pid not in P: pid = "r" + secrets.token_hex(3)
        P[pid] = data; cog.save()
        if data.get("message_id") and (ch := g.get_channel(int(data["channel"]))):
            try: await cog.publish(g, pid, data, ch)
            except Exception: pass
        return J({"id": pid})

    async def rr_delete(request):
        e, g, cog = rrc(request)
        if e: return e
        p = cog.g(g.id).pop(request.match_info["pid"], None); cog.save()
        if p and p.get("message_id"):
            try: await (await g.get_channel(int(p["channel"])).fetch_message(int(p["message_id"]))).delete()
            except Exception: pass
        return J({"ok": True})

    async def rr_post(request):
        e, g, cog = rrc(request)
        if e: return e
        pid = request.match_info["pid"]; p = cog.g(g.id).get(pid)
        try: ch = g.get_channel(int((await request.json()).get("channel") or 0))
        except (ValueError, TypeError): ch = None
        if not p or not isinstance(ch, discord.TextChannel): return J({"error": "Save the panel and pick a text channel first"}, status=400)
        try: await cog.publish(g, pid, p, ch)
        except discord.HTTPException: return J({"error": "Discord rejected the message. Check the emojis and my permissions in that channel."}, status=400)
        return J({"ok": True})

    async def logo(request): return web.Response(body=base64.b64decode(LOGO_B64), content_type="image/jpeg", headers={"Cache-Control": "public, no-store"})

    async def index(request): return web.Response(text=INDEX_HTML, content_type="text/html")
    app = web.Application(middlewares=[session_mw])
    app.add_routes([web.get("/", index), web.get("/auth/login", login), web.get("/auth/callback", callback), web.get("/auth/logout", logout),
        web.get("/api/config", config), web.get("/api/me", me), web.get("/api/schema", schema), web.get("/api/guilds", guilds),
        web.get("/api/guilds/{id}", guild_get), web.get("/api/guilds/{id}/overview", overview), web.get("/logo.jpg", logo), web.get("/xypher-pfp.jpg", logo), web.get("/api/guilds/{id}/rroles", rr_list), web.put("/api/guilds/{id}/rroles/{pid}", rr_put), web.delete("/api/guilds/{id}/rroles/{pid}", rr_delete), web.post("/api/guilds/{id}/rroles/{pid}/post", rr_post), web.get("/api/guilds/{id}/giveaways", gw_list), web.post("/api/guilds/{id}/giveaways", gw_start), web.post("/api/guilds/{id}/giveaways/{gid}/{act}", gw_act), web.delete("/api/guilds/{id}/giveaways/{gid}", gw_del), web.get("/api/guilds/{id}/inviters", inviters), web.get("/api/guilds/{id}/cases", cases_get), web.put("/api/guilds/{id}/cases/{cid}", case_put), web.delete("/api/guilds/{id}/cases/{cid}", case_delete), web.get("/api/guilds/{id}/templates", tpl_get), web.put("/api/guilds/{id}/templates/{tid}", tpl_put), web.delete("/api/guilds/{id}/templates/{tid}", tpl_delete), web.post("/api/guilds/{id}/templates/{tid}/send", tpl_send), web.get("/api/guilds/{id}/panels", panels_get), web.put("/api/guilds/{id}/panels/{pid}", panel_put), web.delete("/api/guilds/{id}/panels/{pid}", panel_delete), web.post("/api/guilds/{id}/panels/{pid}/post", panel_post), web.post("/api/guilds/{id}/announce", announce), web.put("/api/guilds/{id}/{sec}", section_put)])
    from urllib.parse import urlparse
    path = (urlparse(REDIRECT or "").path or "").rstrip("/")
    if path and path not in ("/auth/callback", "") and not any(getattr(r, "resource", None) and r.resource.canonical == path for r in app.router.routes()):
        app.router.add_get(path, callback)   # works even if REDIRECT_URI uses another path, like /callback
    return app

async def start_server(bot):
    if not (os.getenv("CLIENT_SECRET") and os.getenv("REDIRECT_URI")):
        print("[dashboard] CLIENT_SECRET / REDIRECT_URI not set, dashboard not started."); return None
    await load_owners(bot)
    runner = web.AppRunner(build(bot)); await runner.setup()
    port = int(os.getenv("DASHBOARD_PORT") or os.getenv("PORT") or 3000)
    await web.TCPSite(runner, "0.0.0.0", port).start()
    print(f"🛡️ Dashboard running on port {port}")
    return runner

# ================= the page =================
LOGO_B64 = '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'
INDEX_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Xypher Dashboard</title><link rel="icon" href="/xypher-pfp.jpg?v=3">
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&family=Cinzel:wght@600;800&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box}:root{--bg:#0f1217;--panel:#171b22;--line:#2f3641;--tx:#efe8d4;--mu:#9aa1ab;--ac:#c9a227;--acx:#2e2710;--bad:#ff8a8a}
body{margin:0;color:var(--tx);font:15px/1.5 Sora,system-ui,sans-serif;background:var(--bg) url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 .08 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")}
.bgcrest{position:fixed;right:-150px;top:-150px;width:600px;opacity:.16;pointer-events:none;z-index:0;transform:rotate(90deg);animation:breathe 9s ease-in-out infinite}
.bgcrest path{stroke:#c9a227;fill:none;stroke-width:1.2;stroke-dasharray:3000;stroke-dashoffset:3000;animation:draw 4s ease-out forwards}
#app>.wrap{position:relative;z-index:1}
button,input,select,textarea{font:inherit;color:inherit}:focus-visible{outline:2px solid var(--ac);outline-offset:2px}
.hide{display:none!important}
.btn{border:0;border-radius:10px;padding:11px 18px;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block}
.dc{background:#5865F2;color:#fff;padding:14px 26px}.pri{background:var(--ac);color:#fff}.ghost{background:none;border:1px solid var(--line)}
.err{color:var(--bad);margin-top:16px}
header{display:flex;align-items:center;gap:12px;padding:14px 24px;border-bottom:1px solid var(--line)}header b{flex:1}
.av{width:32px;height:32px;border-radius:50%;background:var(--line)}
.wrap{max-width:1020px;margin:0 auto;padding:28px 24px 110px}
.servers{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
.srv{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;display:flex;gap:12px;align-items:center;cursor:pointer;text-align:left;width:100%}
.srv img,.srv i{width:44px;height:44px;border-radius:12px;background:var(--line);display:grid;place-items:center;font-style:normal;font-weight:700;flex:none}
.srv small{display:block;color:var(--mu)}
.layout{display:grid;grid-template-columns:190px 1fr;gap:28px}
nav{display:flex;flex-direction:column;gap:4px;position:sticky;top:16px;align-self:start}
nav button{background:none;border:0;text-align:left;padding:10px 12px;border-radius:9px;cursor:pointer;color:var(--mu)}
nav button.on{background:var(--acx);color:var(--ac);font-weight:600}
h2{margin:0 0 16px;font-size:1.5rem;letter-spacing:-.02em}h3{margin:22px 0 0;font-size:.95rem;color:var(--mu);font-weight:600}
.sec{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:4px 20px;margin-top:8px}
.row{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:15px 0;border-bottom:1px solid var(--line)}
.row:last-child{border:0}.row label{font-weight:600}.row small{display:block;color:var(--mu);font-weight:400}
.row.col{flex-direction:column;align-items:stretch;gap:8px}
input[type=text],input[type=number],select,textarea{background:var(--bg);border:1px solid var(--line);border-radius:9px;padding:9px 11px;width:100%;max-width:300px}
.col input,.col textarea{max-width:none}textarea{min-height:90px;resize:vertical}input[type=color]{width:56px;height:38px;border:1px solid var(--line);border-radius:9px;background:var(--bg);padding:3px}
.chips{display:flex;flex-wrap:wrap;gap:6px;max-height:150px;overflow:auto}
.chips label{font-weight:400;border:1px solid var(--line);border-radius:99px;padding:3px 11px;cursor:pointer;font-size:.85rem}
.chips label:has(input:checked){background:var(--acx);border-color:var(--ac);color:var(--ac)}.chips input{display:none}
.sw{position:relative;width:44px;height:25px;flex:none}.sw input{position:absolute;inset:0;opacity:0;margin:0;cursor:pointer;z-index:1}
.sw span{position:absolute;inset:0;background:var(--line);border-radius:99px;transition:.15s}
.sw span:after{content:"";position:absolute;top:3px;left:3px;width:19px;height:19px;background:#fff;border-radius:50%;transition:.15s}
.sw input:checked+span{background:var(--ac)}.sw input:checked+span:after{transform:translateX(19px)}
.sw input:focus-visible+span{outline:2px solid var(--ac);outline-offset:2px}
@media(max-width:720px){.layout{grid-template-columns:1fr}nav{flex-direction:row;overflow-x:auto;position:static}nav button{white-space:nowrap}.row{flex-wrap:wrap}}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}.cord{height:clamp(10px,calc(50vh - 300px),300px)}.login .in{opacity:1!important;transform:none!important}.bgcrest path{stroke-dashoffset:0}}
.login{min-height:100vh;display:grid;place-items:center;padding:24px;text-align:center;position:relative;overflow:hidden;color:#ececf4;background:radial-gradient(120% 80% at 50% 0%,#232a38 0%,#0a0c10 62%)}
.login>svg{position:absolute;top:-50px;left:-70px;width:min(75vw,640px);opacity:.3;pointer-events:none}
.login>svg.r{left:auto;top:auto;right:-130px;bottom:-130px;transform:rotate(180deg)}
.login>svg path{stroke:#c9a227;fill:none;stroke-width:1}
@keyframes rise{to{opacity:1;transform:none}}
.login .in{position:relative;opacity:0;transform:translateY(14px);animation:rise .7s 1.1s forwards}
.login h1{font-size:clamp(3.4rem,13vw,7rem);font-weight:800;letter-spacing:-.055em;line-height:.9;margin:0 0 16px}
.login p{color:#a9acc9;margin:0 auto 28px;max-width:38ch}
.login small{display:block;margin-top:16px;color:#7d80a0}
.login .dc{box-shadow:0 8px 30px #5865f255;transition:transform .15s}.login .dc:hover{transform:translateY(-2px)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}.stat b{display:block;font-size:1.7rem;letter-spacing:-.02em}.stat small{color:var(--mu)}
.row.st>div{flex:1}.dot{width:10px;height:10px;border-radius:50%;background:var(--line);flex:none}.dot.on{background:#3ddc84}
.meter{width:min(240px,40%);height:8px;border-radius:9px;background:var(--line);overflow:hidden;flex:none}.meter i{display:block;height:100%;width:var(--w);background:var(--ac)}
.empty{padding:26px 0;color:var(--mu);text-align:center}
@keyframes draw{to{stroke-dashoffset:0}}@keyframes breathe{50%{opacity:.26;transform:rotate(94deg) scale(1.04)}}
@keyframes sway{0%,100%{transform:rotate(-3.5deg)}50%{transform:rotate(3.5deg)}}
@keyframes cord{to{height:clamp(10px,calc(50vh - 300px),300px)}}
@keyframes pop{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
@keyframes pulse{50%{box-shadow:0 0 0 5px #3ddc8422}}
.hang{position:absolute;top:0;left:50%;margin-left:-58px;width:116px;display:flex;flex-direction:column;align-items:center;transform-origin:50% 0;animation:sway 5s ease-in-out 2s infinite}
.cord{width:4px;height:0;background:repeating-linear-gradient(#d9c46a 0 7px,#5b4a14 7px 10px);animation:cord 1.5s cubic-bezier(.3,.7,.2,1) forwards}
.medal{width:112px;height:112px;border-radius:50%;object-fit:cover;border:3px solid #c9a227;box-shadow:0 0 44px #c9a22777;margin-top:-3px}
.logo{width:36px;height:36px;border-radius:50%;border:2px solid var(--ac);box-shadow:0 0 14px #c9a22766}
header{background:#121215cc;backdrop-filter:blur(8px);position:sticky;top:0;z-index:5}
.pri{box-shadow:0 6px 22px #c9a22744;transition:transform .15s,box-shadow .15s}.pri:hover{transform:translateY(-2px);box-shadow:0 10px 28px #c9a22777}
.btn.ghost:hover{border-color:var(--ac)}
.srv{transition:transform .2s,border-color .2s,box-shadow .2s}.srv:hover{transform:translateY(-4px);border-color:var(--ac);box-shadow:0 12px 32px #c9a22726}
nav button{transition:background .15s,color .15s,padding .15s}nav>button:hover{color:var(--tx);padding-left:16px}nav button.on{box-shadow:inset 3px 0 0 var(--ac)}
#fields>*{animation:pop .4s both}#fields>:nth-child(2){animation-delay:.05s}#fields>:nth-child(3){animation-delay:.1s}#fields>:nth-child(4){animation-delay:.15s}
.sec,.stat,.bcard,.pcard{transition:border-color .2s}.sec:hover,.stat:hover,.pcard:hover{border-color:#c9a22766}
.dot.on{animation:pulse 2s infinite}
.bar-top{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}.hint{color:var(--mu);margin:0}.sm{padding:7px 12px;font-size:.85rem}
.pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px;margin-top:16px}
.pcard{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}.pcard small{display:block;color:var(--mu)}.acts{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
.bcard{background:var(--panel);border:1px solid var(--line);border-radius:14px;margin-top:14px;padding:6px 18px 14px}.bhead{display:flex;justify-content:space-between;align-items:center;padding:10px 0}
.dbtn{display:inline-block;padding:8px 16px;border-radius:8px;font-weight:600;font-size:.9rem;color:#fff;background:#5865f2}.dbtn.secondary{background:#4e5058}.dbtn.success{background:#248046}.dbtn.danger{background:#da373c}
.qcard{border:1px dashed var(--line);border-radius:12px;padding:12px;margin-top:12px;display:grid;gap:8px}.qcard input,.qcard select{max-width:none}
.two{display:grid;grid-template-columns:1fr 1fr;gap:8px}.qrow{display:flex;justify-content:space-between;align-items:center}.qrow label{display:flex;align-items:center;gap:10px;font-weight:400}
.row.st .btn{flex:none}
.toast{color:var(--ac)}.toast.bad{color:var(--bad)}
.wrap{max-width:1180px}.layout{grid-template-columns:240px 1fr}
.hero{margin-bottom:24px}.hero h2{font-size:clamp(1.9rem,5vw,2.8rem);letter-spacing:-.035em;margin:0 0 6px}.hero p{color:var(--mu);margin:0 0 18px}
#q{max-width:380px}
.servers{grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px}
.srv{position:relative;overflow:hidden;flex-direction:column;align-items:flex-start;gap:14px;padding:20px;min-height:158px;animation:pop .45s both}
.srv::before{content:"";position:absolute;inset:-24px;background:var(--ic,none) center/cover;opacity:.2;filter:blur(24px);z-index:0}
.srv>*{position:relative;z-index:1}.srv img,.srv i{width:62px;height:62px;border-radius:18px;font-size:1.6rem}
.srv b{font-size:1.05rem;display:block}.srv .go{margin-top:auto;font-size:.85rem;font-weight:600;color:var(--ac)}
.srv.off{border-style:dashed}.srv.off .go{color:var(--mu)}
nav>button{display:flex;align-items:center;gap:10px}.ico{width:22px;text-align:center}
.ng{margin:18px 0 4px 12px;font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;color:var(--mu)}
.nsrv{display:flex;align-items:center;gap:10px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:10px;margin-bottom:6px}
.nsrv img,.nsrv i{width:38px;height:38px;border-radius:11px;background:var(--line);display:grid;place-items:center;font-style:normal;font-weight:700;flex:none}
.nsrv div{flex:1;min-width:0}.nsrv b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.nsrv small{color:var(--mu)}
#secDesc{margin:-8px 0 18px}
.qa{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:12px}
.qa button{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;text-align:left;cursor:pointer;font-weight:600;transition:transform .2s,border-color .2s}
.qa button:hover{transform:translateY(-3px);border-color:var(--ac)}.qa small{display:block;color:var(--mu);font-weight:400}
.pop{position:fixed;left:50%;bottom:24px;z-index:20;display:flex;align-items:center;gap:12px;padding:9px 9px 9px 22px;background:#1d1d23f2;backdrop-filter:blur(12px);border:1px solid #c9a22777;border-radius:99px;box-shadow:0 16px 50px #000a,0 0 30px #c9a22733;transform:translate(-50%,180%);opacity:0;transition:transform .45s cubic-bezier(.2,1.3,.4,1),opacity .25s,border-color .2s;max-width:calc(100vw - 20px);white-space:nowrap}
.pop.show{transform:translate(-50%,0);opacity:1}.pop .btn{padding:9px 22px;border-radius:99px;min-width:84px;text-align:center}
#popmsg{font-weight:600;font-size:.9rem}.pop.ok{border-color:#3ddc84aa}.pop.ok #popmsg{color:#3ddc84}.pop.bad #popmsg{color:var(--bad)}
.dots{display:none;gap:5px;align-items:center;justify-content:center;height:20px}.dots i{width:7px;height:7px;border-radius:50%;background:#fff;animation:bounce 1s infinite}
.dots i:nth-child(2){animation-delay:.15s}.dots i:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,60%,100%{transform:translateY(0);opacity:.45}30%{transform:translateY(-6px);opacity:1}}
.pop.saving .dots{display:flex}.pop.saving #savetxt{display:none}.pop.saving .btn{pointer-events:none}.pop.saving #reset{opacity:.4}
@media(max-width:720px){.ng,.nsrv{display:none}.pop{gap:8px;padding-left:16px;bottom:14px}#popmsg{font-size:.8rem}.pop .btn{padding:8px 14px;min-width:0}}
.prog{position:fixed;top:0;left:0;height:3px;width:0;opacity:0;background:linear-gradient(90deg,#c9a227,#f0d77a);box-shadow:0 0 12px #c9a227;z-index:60;transition:width .5s ease,opacity .3s}
.btn{position:relative;overflow:hidden}.btn:active{transform:scale(.97)}
.ripple{position:absolute;border-radius:50%;background:#ffffff55;transform:scale(0);animation:rip .6s ease-out forwards;pointer-events:none}
@keyframes rip{to{transform:scale(4);opacity:0}}
.srv,.stat,.pcard,.qa button,.sec,.bcard{position:relative;background-image:radial-gradient(260px circle at var(--mx,-999px) var(--my,-999px),#c9a22724,transparent 62%)}
.glide{position:absolute;left:0;top:0;width:100%;height:0;border-radius:9px;background:var(--acx);box-shadow:inset 3px 0 0 var(--ac);transition:transform .38s cubic-bezier(.3,1.25,.4,1),height .3s,opacity .2s;pointer-events:none;animation:none!important}
nav>button{position:relative;z-index:1}nav button.on{background:none;box-shadow:none;color:var(--ac);font-weight:600}nav>*{animation:pop .4s both}
.sec>.row{animation:pop .35s both}.sec>.row:nth-child(1){animation-delay:0.03s}.sec>.row:nth-child(2){animation-delay:0.06s}.sec>.row:nth-child(3){animation-delay:0.09s}.sec>.row:nth-child(4){animation-delay:0.12s}.sec>.row:nth-child(5){animation-delay:0.15s}.sec>.row:nth-child(6){animation-delay:0.18s}.sec>.row:nth-child(7){animation-delay:0.21s}.sec>.row:nth-child(8){animation-delay:0.24s}.sec>.row:nth-child(9){animation-delay:0.27s}.sec>.row:nth-child(10){animation-delay:0.30s}.sec>.row:nth-child(11){animation-delay:0.33s}.sec>.row:nth-child(12){animation-delay:0.36s}
.skel{height:78px;border-radius:14px;margin-top:12px;background:linear-gradient(90deg,var(--panel) 25%,#2a2a32 50%,var(--panel) 75%);background-size:200% 100%;animation:shim 1.2s linear infinite}
@keyframes shim{to{background-position:-200% 0}}
.sw span:after{transition:transform .35s cubic-bezier(.3,1.6,.5,1)}
.pop.ok #popmsg::before{content:"\2713  ";display:inline-block;animation:tick .45s cubic-bezier(.3,1.8,.5,1)}@keyframes tick{from{transform:scale(0) rotate(-45deg)}}
.fs{position:relative;width:min(300px,36vw);display:none}.fs.on{display:block}.fs input{width:100%;max-width:none;padding-top:8px;padding-bottom:8px}
.fsres{position:absolute;top:calc(100% + 8px);left:0;right:0;background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden;display:none;z-index:30;box-shadow:0 16px 44px #000b}
.fsres.open{display:block;animation:pop .2s both}.fsres button{display:flex;gap:10px;width:100%;padding:11px 14px;background:none;border:0;text-align:left;cursor:pointer}.fsres button:hover{background:var(--acx)}
.row.case{cursor:pointer;transition:background .15s}.row.case:hover{background:#ffffff08}.row.case>div{flex:1}.row.case .go{color:var(--mu);font-size:.85rem;transition:transform .2s,color .2s}.row.case:hover .go{transform:translateX(4px);color:var(--ac)}
.fl{margin:14px 0 8px}
.tgrid{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:22px;align-items:start}.prev{position:sticky;top:76px}
.dmsg{background:#313338;border-radius:12px;padding:16px;color:#dbdee1;font-family:system-ui,sans-serif;font-size:.92rem}
.dhead{display:flex;align-items:center;gap:8px;margin-bottom:6px}.dhead img{width:34px;height:34px;border-radius:50%}.dhead b{color:#fff}.tag{background:#5865f2;color:#fff;font-size:.65rem;padding:1px 5px;border-radius:4px}
.dtext{white-space:pre-wrap;margin:4px 0 8px;overflow-wrap:anywhere}
.emb{display:flex;gap:12px;background:#2b2d31;border-left:4px solid #c9a227;border-radius:4px;padding:10px 12px;margin-top:8px}
.embody{flex:1;min-width:0}.eau{font-size:.8rem;font-weight:600;margin-bottom:4px}.eti{font-weight:700;color:#fff;margin-bottom:4px;overflow-wrap:anywhere}.ede{white-space:pre-wrap;font-size:.88rem;overflow-wrap:anywhere}
.efs{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px}.ef{grid-column:1/-1;font-size:.85rem}.ef.in{grid-column:auto}.ef b{display:block;color:#fff;font-size:.82rem}
.eim{max-width:100%;border-radius:6px;margin-top:10px}.eth{width:64px;height:64px;object-fit:cover;border-radius:6px}.eft{font-size:.72rem;color:#b5bac1;margin-top:8px}.dbtns{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
@media(max-width:1000px){.tgrid{grid-template-columns:1fr}.prev{position:static}}
@media(max-width:720px){.glide{display:none}nav button.on{background:var(--acx)}.fs{width:40vw}}
header{position:sticky;top:0}
.pop{position:fixed}
html,body{height:100%;overflow:hidden}
#app{height:100vh;height:100dvh;display:flex;flex-direction:column}
#app>header{position:relative;flex:none}
#app>.wrap{flex:1;min-height:0;overflow:hidden;width:100%;padding-bottom:0;display:flex;flex-direction:column}
#picker{flex:1;min-height:0;overflow-y:auto;padding-bottom:48px;scrollbar-width:thin}
#panel:not(.hide){flex:1;min-height:0;display:flex;flex-direction:column}
.layout{flex:1;min-height:0;grid-template-columns:240px minmax(0,1fr);grid-template-rows:minmax(0,1fr)}
.layout nav{position:relative;top:auto;align-self:stretch;max-height:none;min-height:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;padding-bottom:32px}
#main{min-height:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;padding:0 8px 140px 0}
.prev{top:12px}
.login{height:100vh;height:100dvh;overflow-x:hidden;overflow-y:auto}
@media(max-width:720px){.layout{grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr)}.layout nav{flex-direction:row;overflow-x:auto;overflow-y:hidden;padding:6px 0;align-self:start}#app>.wrap{padding:16px 14px 0}#main{padding-right:0}}
.keep{display:inline-flex;align-items:center;gap:10px;margin-top:20px;cursor:pointer;color:#a9acc9;font-size:.9rem;user-select:none;position:relative}
.keep input{position:absolute;opacity:0;width:0;height:0}
.keep .box{width:22px;height:22px;border-radius:7px;border:2px solid #5b5d7a;display:grid;place-items:center;transition:background .2s,border-color .2s,transform .2s,box-shadow .2s}
.keep .box svg{width:16px;height:16px;fill:none;stroke:#fff;stroke-width:3;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:24;stroke-dashoffset:24;transition:stroke-dashoffset .3s .05s}
.keep input:checked+.box{background:#c9a227;border-color:#c9a227;box-shadow:0 0 16px #c9a22788}.keep input:checked+.box svg{stroke-dashoffset:0}
.keep:active .box{transform:scale(.86)}.keep input:focus-visible+.box{outline:2px solid #fff;outline-offset:2px}
.spl{display:grid;justify-items:center;gap:8px;padding:48px 0;color:var(--mu)}
.spl .thr{display:flex;flex-direction:column;align-items:center;transform-origin:50% 0;animation:bob 1.8s ease-in-out infinite}
.spl .thr i{width:2px;height:40px;background:repeating-linear-gradient(#d9c46a 0 7px,#5b4a14 7px 10px)}
.lg path{fill:none;stroke:#c9a227;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}.bd{fill:#c9a227}
.lg{transform-origin:24px 27px;animation:legs .4s ease-in-out infinite alternate}.lg.r{animation-direction:alternate-reverse}
@keyframes legs{from{transform:rotate(-8deg)}to{transform:rotate(8deg)}}@keyframes bob{0%,100%{transform:translateY(-16px)}50%{transform:translateY(8px)}}
.boot{position:fixed;inset:0;z-index:100;display:grid;place-items:center;background:#0a0c10;color:#a9acc9;transition:opacity .45s}.boot.gone{opacity:0;pointer-events:none}
html{color-scheme:dark}
input[type=search]{-webkit-appearance:none;appearance:none;width:100%;background:#0c0f14 url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23a69a9d' stroke-width='2.4' stroke-linecap='round'><circle cx='11' cy='11' r='7'/><path d='M20 20l-3.5-3.5'/></svg>") no-repeat 15px center/18px;color:var(--tx);-webkit-text-fill-color:var(--tx);caret-color:var(--ac);border:1px solid var(--line);border-radius:99px;padding:11px 16px 11px 44px;transition:border-color .2s,box-shadow .2s,background-color .2s}
input[type=search]::placeholder{color:var(--mu);-webkit-text-fill-color:var(--mu);opacity:1}
input[type=search]:hover{border-color:#c9a22766}
input[type=search]:focus{outline:none;border-color:var(--ac);box-shadow:0 0 0 3px #c9a22733;background-color:#15151a}
input[type=search]::-webkit-search-decoration,input[type=search]::-webkit-search-results-button{display:none}
input[type=search]::-webkit-search-cancel-button{-webkit-appearance:none;width:18px;height:18px;border-radius:50%;cursor:pointer;background:#3a2a2f url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23f2eced' stroke-width='3' stroke-linecap='round'><path d='M6 6l12 12M18 6L6 18'/></svg>") center/10px no-repeat}
input:-webkit-autofill,textarea:-webkit-autofill{-webkit-box-shadow:0 0 0 100px #0c0f14 inset;-webkit-text-fill-color:var(--tx)}
header{gap:12px}header #title{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.um{position:relative;flex:none}.avb{background:none;border:0;padding:0;cursor:pointer;border-radius:50%;display:block}
.avb .av{display:block;border:2px solid var(--line);transition:border-color .2s,transform .2s}.avb:hover .av{border-color:var(--ac);transform:scale(1.06)}
.umenu{position:absolute;right:0;top:calc(100% + 12px);min-width:200px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;display:none;gap:14px;box-shadow:0 16px 44px #000b;z-index:50}
.umenu.open{display:grid;animation:pop .2s both}.uname{font-weight:600;overflow-wrap:anywhere}.umenu small{color:var(--mu)}
.ib{display:none;width:38px;height:38px;flex:none;border-radius:50%;border:1px solid var(--line);background:none;cursor:pointer;place-items:center}
.ib svg{width:18px;height:18px;fill:none;stroke:var(--tx);stroke-width:2.2;stroke-linecap:round}
@media(max-width:720px){
  header{padding:10px 14px;gap:10px}header #title{font-size:1rem}
  header:has(.fs.on) .ib{display:grid}.fs.on{display:none}
  .fs.on.open{display:block;position:absolute;left:0;right:0;top:100%;width:auto;padding:10px 14px;background:#0f1217f5;border-bottom:1px solid var(--line);z-index:40;animation:pop .2s both}
  .fs.open .fsres{left:14px;right:14px;top:calc(100% - 2px)}
}
.mbar{display:none;flex:none;align-items:center;gap:12px;padding:0 0 14px}
.mb{width:44px;height:44px;border-radius:12px;border:1px solid var(--line);background:var(--panel);display:grid;place-items:center;cursor:pointer;transition:border-color .2s,transform .2s}
.mb:hover{border-color:var(--ac)}.mb:active{transform:scale(.9)}.mb svg{width:20px;height:20px;fill:none;stroke:var(--tx);stroke-width:2.4;stroke-linecap:round}
#mtitle{font-weight:600;font-size:1.05rem}
.scrim{position:fixed;inset:0;z-index:70;background:#000b;backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px);opacity:0;pointer-events:none;transition:opacity .3s}.scrim.show{opacity:1;pointer-events:auto}
@media(max-width:720px){
  #app>.wrap{z-index:auto}
  .mbar{display:flex}
  .layout{grid-template-columns:minmax(0,1fr);grid-template-rows:minmax(0,1fr)}
  .layout nav{position:fixed;left:0;top:0;bottom:0;width:min(84vw,320px);z-index:80;flex-direction:column;overflow-x:hidden;overflow-y:auto;padding:18px 14px 36px;background:var(--panel);border-right:1px solid var(--line);box-shadow:0 0 60px #000c;transform:translateX(-105%);transition:transform .35s cubic-bezier(.3,1,.4,1);align-self:auto}
  .layout nav.open{transform:none}
  .ng{display:block}.nsrv{display:flex}.glide{display:block}
  nav button{white-space:normal}nav button.on{background:none}
}
.greet{animation:pop .5s both;margin-bottom:6px}
.greet h1{font-size:clamp(1.7rem,5.5vw,2.7rem);letter-spacing:-.035em;line-height:1.1;margin:0 0 6px;overflow-wrap:anywhere}
.greet .nm{color:var(--ac);text-shadow:0 0 28px #c9a22755}
.greet p{color:var(--mu);margin:0 0 22px}
.wave{display:inline-block;transform-origin:70% 75%;animation:wave 2.4s ease-in-out .6s 2}
@keyframes wave{0%,60%,100%{transform:rotate(0)}10%{transform:rotate(16deg)}20%{transform:rotate(-8deg)}30%{transform:rotate(16deg)}40%{transform:rotate(-4deg)}50%{transform:rotate(10deg)}}
.tplgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px;margin-top:4px}
.tplcard{position:relative;display:grid;gap:10px;text-align:left;cursor:pointer;color:var(--tx);background:var(--bg);border:2px solid var(--line);border-radius:16px;padding:14px;transition:transform .2s,border-color .2s,box-shadow .2s}
.tplcard:hover{transform:translateY(-3px);border-color:#c9a22788}
.tplcard.sel{border-color:var(--ac);box-shadow:0 0 0 3px #c9a22733,0 12px 30px #c9a22722}
.tplcard.sel::after{content:"\2713";position:absolute;top:10px;right:12px;width:22px;height:22px;border-radius:50%;background:var(--ac);color:#fff;display:grid;place-items:center;font-size:.8rem;animation:tick .4s cubic-bezier(.3,1.8,.5,1)}
.dmsg.mini{padding:10px;font-size:.82rem;pointer-events:none}.eth.fake{display:grid;place-items:center;background:#5865f2;color:#fff;font-weight:700;border-radius:50%;width:44px;height:44px;flex:none}
.selmock{background:#1e1f22;border:1px solid #3f4147;border-radius:6px;padding:10px 12px;margin-top:8px;color:#b5bac1}
.rx{display:inline-grid;place-items:center;min-width:34px;height:28px;padding:0 8px;border-radius:8px;background:#2b2d31;border:1px solid #3f4147}
.ktrack{position:relative;width:min(300px,70vw);height:64px;overflow:hidden;border-bottom:3px solid #3b4350}
.ktrack .kn{position:absolute;bottom:-2px;font-size:54px;line-height:1;color:#c9a227;filter:drop-shadow(0 0 10px #c9a22788);animation:kgallop 2.2s linear infinite,kbob .3s ease-in-out infinite}
@keyframes kgallop{from{left:-70px}to{left:100%}}
@keyframes kbob{0%,100%{transform:scaleX(-1) translateY(0)}50%{transform:scaleX(-1) translateY(-7px) rotate(5deg)}}
.login h1,.greet h1,header b{font-family:Cinzel,Sora,serif}.login h1{letter-spacing:.05em;color:#e9d27a;text-shadow:0 0 40px #c9a22766}
body::after{content:"";position:fixed;left:0;right:0;bottom:0;height:36vh;z-index:0;pointer-events:none;opacity:.3;background:url("data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%201200%20220%22%20preserveAspectRatio%3D%22xMidYMax%20slice%22%3E%3Cg%20fill%3D%22%2306070a%22%3E%3Crect%20x%3D%220%22%20y%3D%22176%22%20width%3D%221200%22%20height%3D%2244%22/%3E%3Crect%20x%3D%220%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%2236%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%2272%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22108%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22144%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22180%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22216%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22252%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22288%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22324%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22360%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22396%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22432%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22468%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22504%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22540%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22576%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22612%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22648%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22684%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22720%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22756%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22792%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22828%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22864%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22900%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22936%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%22972%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%221008%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%221044%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%221080%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%221116%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%221152%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%221188%22%20y%3D%22162%22%20width%3D%2220%22%20height%3D%2216%22/%3E%3Crect%20x%3D%2260%22%20y%3D%22112%22%20width%3D%2270%22%20height%3D%22108%22/%3E%3Crect%20x%3D%2260%22%20y%3D%2298%22%20width%3D%228%22%20height%3D%2215%22/%3E%3Crect%20x%3D%2274%22%20y%3D%2298%22%20width%3D%228%22%20height%3D%2215%22/%3E%3Crect%20x%3D%2288%22%20y%3D%2298%22%20width%3D%228%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22102%22%20y%3D%2298%22%20width%3D%228%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22116%22%20y%3D%2298%22%20width%3D%228%22%20height%3D%2215%22/%3E%3Cpolygon%20points%3D%2277%2C98%2095%2C54%20113%2C98%22/%3E%3Crect%20x%3D%22260%22%20y%3D%2274%22%20width%3D%2286%22%20height%3D%22146%22/%3E%3Crect%20x%3D%22260%22%20y%3D%2260%22%20width%3D%2210%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22277%22%20y%3D%2260%22%20width%3D%2210%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22294%22%20y%3D%2260%22%20width%3D%2210%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22312%22%20y%3D%2260%22%20width%3D%2210%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22329%22%20y%3D%2260%22%20width%3D%2210%22%20height%3D%2215%22/%3E%3Cpolygon%20points%3D%22285%2C60%20303%2C16%20321%2C60%22/%3E%3Crect%20x%3D%22520%22%20y%3D%2234%22%20width%3D%22120%22%20height%3D%22186%22/%3E%3Crect%20x%3D%22520%22%20y%3D%2220%22%20width%3D%2214%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22544%22%20y%3D%2220%22%20width%3D%2214%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22568%22%20y%3D%2220%22%20width%3D%2214%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22592%22%20y%3D%2220%22%20width%3D%2214%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22616%22%20y%3D%2220%22%20width%3D%2214%22%20height%3D%2215%22/%3E%3Cpolygon%20points%3D%22562%2C20%20580%2C-24%20598%2C20%22/%3E%3Crect%20x%3D%22800%22%20y%3D%2284%22%20width%3D%2284%22%20height%3D%22136%22/%3E%3Crect%20x%3D%22800%22%20y%3D%2270%22%20width%3D%2210%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22817%22%20y%3D%2270%22%20width%3D%2210%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22834%22%20y%3D%2270%22%20width%3D%2210%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22850%22%20y%3D%2270%22%20width%3D%2210%22%20height%3D%2215%22/%3E%3Crect%20x%3D%22867%22%20y%3D%2270%22%20width%3D%2210%22%20height%3D%2215%22/%3E%3Cpolygon%20points%3D%22824%2C70%20842%2C26%20860%2C70%22/%3E%3Crect%20x%3D%221040%22%20y%3D%22108%22%20width%3D%2278%22%20height%3D%22112%22/%3E%3Crect%20x%3D%221040%22%20y%3D%2294%22%20width%3D%229%22%20height%3D%2215%22/%3E%3Crect%20x%3D%221056%22%20y%3D%2294%22%20width%3D%229%22%20height%3D%2215%22/%3E%3Crect%20x%3D%221071%22%20y%3D%2294%22%20width%3D%229%22%20height%3D%2215%22/%3E%3Crect%20x%3D%221087%22%20y%3D%2294%22%20width%3D%229%22%20height%3D%2215%22/%3E%3Crect%20x%3D%221102%22%20y%3D%2294%22%20width%3D%229%22%20height%3D%2215%22/%3E%3Cpolygon%20points%3D%221061%2C94%201079%2C50%201097%2C94%22/%3E%3C/g%3E%3Cg%20fill%3D%22%23c9a227%22%20opacity%3D%22.55%22%3E%3Crect%20x%3D%2290%22%20y%3D%22136%22%20width%3D%2210%22%20height%3D%2222%22%20rx%3D%225%22/%3E%3Crect%20x%3D%22298%22%20y%3D%2298%22%20width%3D%2210%22%20height%3D%2222%22%20rx%3D%225%22/%3E%3Crect%20x%3D%22575%22%20y%3D%2258%22%20width%3D%2210%22%20height%3D%2222%22%20rx%3D%225%22/%3E%3Crect%20x%3D%22837%22%20y%3D%22108%22%20width%3D%2210%22%20height%3D%2222%22%20rx%3D%225%22/%3E%3Crect%20x%3D%221074%22%20y%3D%22132%22%20width%3D%2210%22%20height%3D%2222%22%20rx%3D%225%22/%3E%3C/g%3E%3C/svg%3E") bottom center/cover no-repeat}
#login{z-index:1}
</style></head><body>
<div class="prog" id="prog"></div><div class="scrim" id="scrim"></div><div class="boot" id="boot"></div>
<section id="login" class="login hide"><div class="hang"><i class="cord"></i><img class="medal" src="/xypher-pfp.jpg?v=3" alt="Xypher"></div><div class="in">
  <h1>Xypher</h1>
  <p>Your server's control room. Tune AutoMod, welcomes, levels and tickets here instead of typing commands.</p>
  <a class="btn dc" id="dclogin" href="/auth/login?remember=1">Log in with Discord</a>
  <div><label class="keep"><input type="checkbox" id="keep" checked><span class="box"><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></span>Keep me logged in on this device</label></div>
  <small>We only read your name and the list of servers you manage.</small><div id="loginErr" class="err"></div>
</div></section>
<section id="app" class="hide">
  <header><img class="logo" id="hlogo" src="/xypher-pfp.jpg?v=3" alt=""><b id="title">Xypher Dashboard</b>
    <button class="ib" id="fsbtn" aria-label="Search features"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg></button>
    <div class="fs" id="fs"><input id="fsearch" type="search" placeholder="Search features (press /)" autocomplete="off"><div class="fsres" id="fsres"></div></div>
    <div class="um" id="um"><button class="avb" id="avb" aria-label="Account menu"><img class="av" id="uav" alt=""></button>
      <div class="umenu" id="umenu"><div><small>Signed in as</small><div class="uname" id="uname"></div></div><a class="btn ghost sm" href="/auth/logout">Log out</a></div></div>
  </header>
  <div class="wrap">
    <div id="picker"><div class="hero"><h2 id="hello">Hey</h2><p>Pick a server to manage. Servers with Xypher come first.</p><input id="q" type="search" placeholder="Search your servers"></div><div class="servers" id="servers"></div></div>
    <div id="panel" class="hide"><div class="mbar"><button class="mb" id="menubtn" aria-label="Open menu"><svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h10"/></svg></button><span id="mtitle"></span></div><div class="layout"><nav id="nav"></nav><div id="main"><div class="greet hide" id="greet"></div><h2 id="secTitle"></h2><p class="hint" id="secDesc"></p><div id="fields"></div></div></div></div>
  </div>
  <div class="pop" id="bar" role="status"><span id="popmsg">You have unsaved changes</span><button class="btn ghost" id="reset">Reset</button><button class="btn pri" id="save"><span id="savetxt">Save</span><span class="dots"><i></i><i></i><i></i></span></button></div>
</section>
<script>
const $=id=>document.getElementById(id);
let _p=0;const prog=d=>{_p+=d;const b=$('prog');if(!b)return;if(_p>0){b.style.opacity=1;b.style.width='72%'}else{_p=0;b.style.width='100%';setTimeout(()=>{b.style.opacity=0;setTimeout(()=>{b.style.width='0'},300)},250)}};
const api=async(u,o)=>{prog(1);try{const r=await fetch(u,o);const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'Request failed');return j}finally{prog(-1)}};
let SCHEMA=[],CID='',G=null,META=null,VAL={},ORIG={},TAB='',ready=false;
const clone=o=>JSON.parse(JSON.stringify(o));
const isDirty=()=>!!ORIG[TAB]&&JSON.stringify(VAL[TAB])!==JSON.stringify(ORIG[TAB]);
let CTL=null,busy=false,PREV=null;
async function init0(){
  const q=new URLSearchParams(location.search).get('error');
  const {user,owner}=await api('/api/me');
  if(!user){$('login').classList.remove('hide');if(q)$('loginErr').textContent=q==='state'?'Login expired. Try again.':'Discord login failed. Try again.';return}
  [SCHEMA,{clientId:CID}]=await Promise.all([api('/api/schema'),api('/api/config')]);
  $('app').classList.remove('hide');$('uname').textContent=(user.global_name||user.username)+(owner?' (Owner)':'');window.ME=user.global_name||user.username;$('hello').textContent='Hey, '+window.ME;
  $('uav').src=user.avatar?`https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png?size=64`:`https://cdn.discordapp.com/embed/avatars/${Number((BigInt(user.id)>>22n)%6n)}.png`;
  loadServers();
}
async function loadServers(){
  const box=$('servers');box.innerHTML='';box.append(spl('Finding your servers'));let gs;
  try{gs=await api('/api/guilds')}catch(e){box.textContent=e.message;return}
  const draw=()=>{const q=$('q').value.trim().toLowerCase();box.innerHTML='';
    const list=gs.filter(g=>g.name.toLowerCase().includes(q)).sort((a,b)=>b.botIn-a.botIn);
    if(!list.length){box.append(el('div','empty',gs.length?'No server matches your search.':'You do not manage any servers yet.'));return}
    list.forEach((g,i)=>{const c=el('button','srv'+(g.botIn?'':' off')),url=g.icon?`https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png?size=128`:'';
      c.style.animationDelay=(i*45)+'ms';if(url)c.style.setProperty('--ic',`url(${url})`);
      const ic=url?el('img'):el('i','',g.name[0]);if(url){ic.src=url;ic.alt=''}
      const t=el('div');t.append(el('b','',g.name),el('small','',g.botIn?`${g.members.toLocaleString()} members${g.viaOwner?', owner access':''}`:'Xypher is not here yet'));
      c.append(ic,t,el('span','go',g.botIn?'Manage server \u2192':'Add Xypher \u2192'));
      c.onclick=()=>g.botIn?openGuild(g):window.open(`https://discord.com/oauth2/authorize?client_id=${CID}&scope=bot%20applications.commands&permissions=8&guild_id=${g.id}`,'_blank');
      box.append(c)})};
  $('q').oninput=draw;draw();
}
const SPECIAL=[['overview','Overview'],['board','Leaderboard'],['cases','Mod cases'],['panels','Ticket panels'],['otickets','Open tickets'],['announce','Announce']];
let TABS=[],OV=null;
const TITLES={rroles:'Reaction roles',giveaways:'Giveaways',invites:'Invite tracker',inviters:'Top inviters',leave:'Leave messages',joinroles:'Join roles',messages:'Messages',overview:'Overview',automod:'AutoMod',welcome:'Welcome',leveling:'Leveling',moderation:'Moderation',utility:'Suggestions',tickets:'Ticket settings',panels:'Ticket panels',otickets:'Open tickets',board:'Leaderboard',cases:'Mod cases',announce:'Announce'};
const ICON={rroles:'\ud83c\udff7\ufe0f',giveaways:'\ud83c\udf89',invites:'\ud83d\udce8',inviters:'\ud83c\udfc5',leave:'\ud83d\udeaa',joinroles:'\ud83c\udfad',messages:'\ud83d\udcac',overview:'\ud83c\udfe0',automod:'\ud83d\udee1\ufe0f',welcome:'\ud83d\udc4b',leveling:'\u2b50',moderation:'\ud83d\udd28',utility:'\ud83d\udca1',tickets:'\u2699\ufe0f',panels:'\ud83c\udfab',otickets:'\ud83d\udceb',board:'\ud83c\udfc6',cases:'\ud83d\udccb',announce:'\ud83d\udce3'};
const DESC={rroles:'Let members pick their own roles with buttons, a menu or emoji reactions.',giveaways:'Start giveaways and let members enter with one button.',invites:'See who invited each new member and post it to a channel.',inviters:'The members who brought in the most people.',leave:'Say goodbye when someone leaves the server.',joinroles:'Roles and checks for brand new members.',messages:'Build reusable messages with embeds and buttons, then send them anywhere.',overview:'A quick look at your server and what Xypher is doing in it.',automod:'Rules that keep your chat clean.',welcome:'Greet new members and say goodbye.',leveling:'XP, levels and role rewards.',moderation:'Where moderation actions are logged.',utility:'Where /suggest posts end up.',tickets:'Default settings for the ticket system.',panels:'Build ticket panels with buttons and forms.',otickets:'Tickets that are open right now.',board:'Your most active members.',cases:'The latest moderation actions.',announce:'Post a message as Xypher.'};
const GROUPS=[['',['overview']],['Modules',['automod','welcome','leave','joinroles','rroles','invites','leveling','moderation','utility']],['Tickets',['tickets','panels','otickets']],['Insights',['board','inviters','cases']],['Tools',['messages','giveaways','announce']]];
const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!==undefined)e.textContent=x;return e};
const when=t=>new Date(t*1000).toLocaleString([], {dateStyle:'medium',timeStyle:'short'});
function setHL(g){const h=$('hlogo');h.onerror=()=>{h.onerror=null;h.src='/xypher-pfp.jpg?v=3'};h.src=g&&g.icon?`https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png?size=64`:'/xypher-pfp.jpg?v=3'}
async function openGuild(g){
  $('servers').innerHTML='';$('servers').append(spl('Opening '+g.name));
  try{[META,OV]=await Promise.all([api('/api/guilds/'+g.id),api(`/api/guilds/${g.id}/overview`)])}catch(e){alert(e.message);loadServers();return}
  G=g;VAL=clone(META.values);ORIG=clone(META.values);
  const have=new Set(['overview','rroles','giveaways','inviters','messages','panels','otickets','board','cases','announce',...SCHEMA.filter(s=>VAL[s.id]).map(s=>s.id)]);
  TABS=GROUPS.flatMap(([,ids])=>ids.filter(i=>have.has(i)).map(i=>[i,TITLES[i]]));TAB='overview';CTL=null;
  $('picker').classList.add('hide');$('panel').classList.remove('hide');$('title').textContent=g.name;$('fs').classList.add('on');setHL(g);
  const nv=$('nav');nv.innerHTML='';
  const nh=el('div','nsrv'),ni=g.icon?el('img'):el('i','',g.name[0]);if(g.icon){ni.src=`https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png?size=64`;ni.alt=''}
  const nt=el('div'),bk=el('button','btn ghost sm','Switch');nt.append(el('b','',g.name),el('small','',`${OV.stats.members} members`));bk.onclick=goBack;nh.append(ni,nt,bk);nv.append(nh);
  GROUPS.forEach(([gn,ids])=>{const vis=ids.filter(i=>have.has(i));if(!vis.length)return;if(gn)nv.append(el('div','ng',gn));
    vis.forEach(i=>{const b=el('button');b.dataset.k=i;b.append(el('span','ico',ICON[i]),TITLES[i]);b.onclick=()=>switchTab(i);nv.append(b)})});
  render();
}
function renderSpecial(k){
  const f=$('fields');f.innerHTML='';$('secTitle').textContent=TABS.find(x=>x[0]===k)[1];
  const list=(rows,empty)=>{if(!rows.length){f.append(el('div','empty',empty));return}const box=el('div','sec');rows.forEach(r=>box.append(r));f.append(box)};
  if(k==='overview'){
    const st=el('div','stats');[['Members',OV.stats.members],['Channels',OV.stats.channels],['Roles',OV.stats.roles],['Bot ping',OV.stats.latency+' ms']].forEach(([a,b])=>{const c=el('div','stat');const bb=el('b','',b);countUp(bb,b);c.append(bb,el('small','',a));st.append(c)});f.append(st);
    f.append(el('h3','','Quick actions'));const qa=el('div','qa');[['panels','Build a ticket panel','Buttons, forms, categories'],['automod','Tune AutoMod','Spam, links, bad words'],['welcome','Set up welcomes','Messages and auto-roles'],['giveaways','Start a giveaway','Winners are picked for you'],['messages','Create a custom message','Embeds and link buttons'],['announce','Send an announcement','Post as Xypher']].filter(([k])=>TABS.some(t=>t[0]===k)).forEach(([k,t,d])=>{const b=el('button');b.append(el('span','',(ICON[k]||'')+' '+t),el('small','',d));b.onclick=()=>switchTab(k);qa.append(b)});f.append(qa);
    f.append(el('h3','','What is switched on'));
    list(OV.status.map(([n,txt,on,tab])=>{const r=el('div','row st'),d=el('div'),b=el('button','btn ghost','Configure');d.append(el('label','',n),el('small','',txt));b.onclick=()=>switchTab(tab);r.append(el('span','dot'+(on?' on':'')),d,b);return r}),'');
  }else if(k==='board'){
    const L=OV.leaderboard||[],top=(L[0]&&L[0].xp)||1;
    list(L.map((u,i)=>{const r=el('div','row'),d=el('div'),m=el('div','meter');d.append(el('label','',`${i+1}. ${u.name}`),el('small','',`Level ${u.level}, ${u.xp} XP, ${u.messages} messages`));m.append(el('i'));m.firstChild.style.setProperty('--w',(u.xp/top*100)+'%');m.style.setProperty('--w','0');r.append(d,m);return r}),'Nobody has earned XP yet. Turn on Leveling and start chatting.');
  }else if(k==='cases'){renderCases();}else if(k==='otickets'){
    list((OV.tickets||[]).map(t=>{const r=el('div','row'),d=el('div');d.append(el('label','',`#${t.number} ${t.subject}`),el('small','',`Opened by ${t.opener} on ${when(t.created)}. ${t.claimed?'Claimed by '+t.claimed:'Not claimed yet'}`));r.append(d);return r}),'No open tickets.');
  }else if(k==='panels'){renderPanels();}else if(k==='messages'){renderMessages();}else if(k==='giveaways'){renderGiveaways();}else if(k==='rroles'){renderRR();}else if(k==='inviters'){renderInviters();}else if(k==='announce'){
    const box=el('div','sec'),mk=(l,h,c)=>{const r=el('div','row col'),d=el('div');d.append(el('label','',l),el('small','',h));r.append(d,c);box.append(r);return c};
    const ch=el('select');META.channels.forEach(o=>ch.add(new Option('#'+o.name,o.id)));mk('Channel','Where Xypher posts it',ch);
    const ti=el('input');ti.type='text';ti.maxLength=200;ti.placeholder='Announcement';mk('Title','',ti);
    const ms=el('textarea');ms.maxLength=3500;mk('Message','Posted as a Xypher-styled embed',ms);
    const go=el('button','btn pri','Send message');go.style.margin='14px 0';box.append(go);f.append(box);const out=el('div','toast');out.style.marginTop='12px';f.append(out);
    go.onclick=async()=>{try{await api(`/api/guilds/${G.id}/announce`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel:ch.value,title:ti.value,message:ms.value})});out.className='toast';out.textContent='Sent.';ms.value=''}catch(e){out.className='toast bad';out.textContent=e.message}};
  }
}
function showGreet(){const g=$('greet');if(TAB!=='overview'){g.classList.add('hide');return}
  g.classList.remove('hide');g.innerHTML='';const t=el('h1');t.append('Welcome, ',el('span','nm',window.ME||'there'),' ',el('span','wave','\ud83d\udc4b'));
  g.append(t,el('p','',`Here is how ${G.name} is doing today.`))}
function drawer(o){$('nav').classList.toggle('open',o);$('scrim').classList.toggle('show',o)}
function switchTab(k){if(cur().dirty()&&!confirm('Discard unsaved changes?'))return;if(ORIG[TAB])VAL[TAB]=clone(ORIG[TAB]);CTL=null;PREV=null;drawer(false);TAB=k;render();touch();$('main').scrollTo({top:0})}
function field(sec,f){
  const row=document.createElement('div');row.className='row'+(f.type==='area'||f.type==='lines'||f.type.startsWith('multi')?' col':'');
  row.innerHTML='<div><label></label><small></small></div>';row.querySelector('label').textContent=f.label;row.querySelector('small').textContent=f.hint||'';
  const v=VAL[sec][f.key],set=x=>{VAL[sec][f.key]=x;touch()};let el;
  if(f.type==='bool'){const w=document.createElement('div');w.className='sw';w.innerHTML='<input type="checkbox" role="switch"><span></span>';el=w.firstChild;el.checked=v;el.onchange=()=>set(el.checked);row.append(w)}
  else if(f.type.startsWith('multi')){const list=f.type==='multirole'?META.roles:META.channels;const box=document.createElement('div');box.className='chips';
    list.forEach(o=>{const l=document.createElement('label'),c=document.createElement('input');c.type='checkbox';c.checked=v.includes(o.id);
      c.onchange=()=>set(list.filter(x=>[...box.querySelectorAll('input')].some((i,n)=>i.checked&&list[n].id===x.id)).map(x=>x.id));
      l.append(c,(f.type==='multirole'?'':'#')+o.name);box.append(l)});row.append(box)}
  else if(f.type==='invtpl'){row.classList.add('col');const grid=el('div','tplgrid');
    f.options.forEach(t=>{const c=el('button','tplcard'+(v===t.id?' sel':''));c.type='button';c.append(el('b','',t.name),tplPrev(t));
      c.onclick=()=>{set(t.id);grid.querySelectorAll('.tplcard').forEach(x=>x.classList.remove('sel'));c.classList.add('sel')};grid.append(c)});row.append(grid)}
  else if(['channel','role','category','select'].includes(f.type)){el=document.createElement('select');
    const list=f.type==='select'?f.options:[['','None'],...(f.type==='role'?META.roles:f.type==='category'?META.categories:META.channels).map(o=>[o.id,(f.type==='channel'?'#':'')+o.name])];
    list.forEach(([a,b])=>el.add(new Option(b,a)));el.value=v;el.onchange=()=>set(el.value);row.append(el)}
  else if(f.type==='lines'||f.type==='area'){el=document.createElement('textarea');el.value=f.type==='lines'?v.join('\n'):v;
    el.oninput=()=>set(f.type==='lines'?el.value.split('\n'):el.value);row.append(el)}
  else if(f.type==='color'){el=document.createElement('input');el.type='color';el.value=v;el.oninput=()=>set(el.value);row.append(el)}
  else{el=document.createElement('input');el.type=f.type==='number'?'number':'text';el.value=v;
    if(f.type==='number'){el.min=f.min;el.max=f.max;el.step=f.float?'0.1':'1'}
    el.oninput=()=>set(f.type==='number'?(el.value===''?f.min:Number(el.value)):el.value);row.append(el)}
  if(el)el.id='f_'+f.key;return row;
}
function render(){
  document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('on',b.dataset.k===TAB));moveGlide();
  $('secDesc').textContent=DESC[TAB]||'';$('mtitle').textContent=TITLES[TAB]||'';showGreet();
  if(!SCHEMA.some(x=>x.id===TAB))return renderSpecial(TAB);
  const s=SCHEMA.find(x=>x.id===TAB);$('secTitle').textContent=TITLES[TAB]||s.title;$('fields').innerHTML='';
  let grp=null,box=null;
  s.fields.forEach(f=>{if(box===null||f.group!==grp){grp=f.group;if(grp){const h=document.createElement('h3');h.textContent=grp;$('fields').append(h)}box=document.createElement('div');box.className='sec';$('fields').append(box)}
    box.append(field(TAB,f))});
}
const saveTab=async()=>{await api(`/api/guilds/${G.id}/${TAB}`,PJ('PUT',VAL[TAB]));ORIG[TAB]=clone(VAL[TAB]);api(`/api/guilds/${G.id}/overview`).then(o=>OV=o).catch(()=>{})};
const cur=()=>CTL||{dirty:isDirty,save:saveTab,reset:()=>{if(ORIG[TAB])VAL[TAB]=clone(ORIG[TAB]);render()}};
function touch(){if(PREV)PREV();if(busy)return;const b=$('bar');b.classList.toggle('show',cur().dirty());b.classList.remove('ok','bad');$('popmsg').textContent='You have unsaved changes'}
$('save').onclick=async()=>{if(busy)return;busy=true;const b=$('bar');b.classList.add('saving');
  try{await Promise.all([cur().save(),new Promise(r=>setTimeout(r,800))]);busy=false;b.classList.remove('saving');b.classList.add('ok');$('popmsg').textContent='Saved. Xypher is using it now.';
    setTimeout(()=>{if(!cur().dirty()){b.classList.remove('show');setTimeout(()=>b.classList.remove('ok'),400)}},1700)}
  catch(e){busy=false;b.classList.remove('saving');b.classList.add('bad');$('popmsg').textContent=e.message}};
$('reset').onclick=()=>{if(busy)return;cur().reset();touch()};
function goBack(){drawer(false);if(cur().dirty()&&!confirm('Discard unsaved changes?'))return;CTL=null;PREV=null;$('fs').classList.remove('on');$('bar').classList.remove('show');$('panel').classList.add('hide');$('picker').classList.remove('hide');$('title').textContent='Xypher Dashboard';setHL(null);loadServers()}
$('fields').addEventListener('input',touch);$('fields').addEventListener('change',touch);
addEventListener('beforeunload',e=>{if(cur().dirty()){e.preventDefault();e.returnValue=''}});
function countUp(n,v){const num=parseFloat(v);if(isNaN(num))return;const suf=String(v).replace(/[\d.]/g,''),t0=performance.now();
  const step=t=>{const p=Math.min(1,(t-t0)/800);n.textContent=Math.round(num*(1-Math.pow(1-p,3)))+suf;if(p<1)requestAnimationFrame(step)};requestAnimationFrame(step)}
const bindv=(o,k,e,ev,g)=>{e.addEventListener(ev||'input',()=>{o[k]=g?g(e):e.value});return e};
const fT=(o,k,max)=>{const e=el('input');e.type='text';e.value=o[k]??'';if(max)e.maxLength=max;return bindv(o,k,e)};
const fA=(o,k)=>{const e=el('textarea');e.value=o[k]??'';return bindv(o,k,e)};
const fN=(o,k,a,b)=>{const e=el('input');e.type='number';e.min=a;e.max=b;e.value=o[k];e.title='Max answer length';return bindv(o,k,e,'input',x=>x.value===''?a:Math.max(a,Math.min(b,Number(x.value))))};
const fS=(o,k,opts)=>{const e=el('select');opts.forEach(([a,b])=>e.add(new Option(b,a)));e.value=o[k];return bindv(o,k,e,'change')};
const fW=(o,k,after)=>{const w=el('div','sw');w.innerHTML='<input type="checkbox" role="switch"><span></span>';const i=w.firstChild;i.checked=!!o[k];i.onchange=()=>{o[k]=i.checked;if(after)after()};return w};
const fR=(p,l,h,c,col)=>{const r=el('div','row'+(col?' col':'')),d=el('div');d.append(el('label','',l),el('small','',h||''));r.append(d,c);p.append(r);return r};
const fC=(o,k,list)=>{const b=el('div','chips');list.forEach(x=>{const l=el('label'),c=el('input');c.type='checkbox';c.checked=o[k].includes(x.id);c.onchange=()=>{o[k]=c.checked?[...o[k],x.id]:o[k].filter(i=>i!==x.id)};l.append(c,x.name);b.append(l)});return b};
const optsOf=(list,none,pre)=>[['',none],...list.map(x=>[x.id,(pre||'')+x.name])];
const newQ=()=>({label:'',style:'short',required:true,placeholder:'',max_length:100});
const newBtn=()=>({label:'Open Ticket',emoji:'\ud83c\udfab',style:'primary',form_enabled:true,form_title:'Open a ticket',questions:[{label:'What do you need help with?',style:'short',required:true,placeholder:'',max_length:100}],ticket_subject:'',ticket_message:''});
const newPanel=()=>({id:'',name:'Support',embed_title:'Need Help?',embed_description:'Press a button below to open a private ticket with our staff.',embed_color:'#c9a227',category:'',support_roles:[],log_channel:'',max_open:1,ticket_message:'',channel:'',buttons:[newBtn()]});
const PJ=(m,b)=>({method:m,headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
async function renderPanels(){
  CTL=null;touch();const f=$('fields');f.innerHTML='';$('secTitle').textContent='Ticket panels';
  skel(f,3);let P;try{P=await api(`/api/guilds/${G.id}/panels`)}catch(e){f.innerHTML='';f.append(el('div','empty',e.message));return}f.innerHTML='';
  const top=el('div','bar-top'),nb=el('button','btn pri','New panel');nb.onclick=()=>panelEditor(null);
  top.append(el('p','hint','A panel is a message with buttons. Every button can ask its own form, then opens a ticket.'),nb);f.append(top);
  if(!P.length){f.append(el('div','empty','No panels yet. Create your first one.'));return}
  const grid=el('div','pgrid');
  P.forEach(p=>{const c=el('div','pcard'),a=el('div','acts'),ed=el('button','btn ghost sm','Edit'),dl=el('button','btn ghost sm','Delete');
    c.append(el('b','',p.name),el('small','',`${p.buttons.length} button${p.buttons.length>1?'s':''}, ${p.message_id?'posted':'not posted yet'}`));
    ed.onclick=()=>panelEditor(p);
    dl.onclick=async()=>{if(!confirm('Delete this panel and its message?'))return;try{await api(`/api/guilds/${G.id}/panels/${p.id}`,{method:'DELETE'});renderPanels()}catch(e){alert(e.message)}};
    a.append(ed,dl);c.append(a);grid.append(c)});
  f.append(grid);
}
function btnCard(D,bt,i,redraw){
  const c=el('div','bcard'),hd=el('div','bhead'),pv=el('span','dbtn');
  const upd=()=>{pv.className='dbtn '+bt.style;pv.textContent=((bt.emoji||'')+' '+(bt.label||'')).trim()};upd();hd.append(pv);
  if(D.buttons.length>1){const rm=el('button','btn ghost sm','Remove button');rm.onclick=()=>{D.buttons.splice(i,1);redraw();touch()};hd.append(rm)}c.append(hd);
  const b=el('div','sec'),lb=fT(bt,'label',80),em=fT(bt,'emoji',32),st=fS(bt,'style',[['primary','Blue'],['secondary','Grey'],['success','Green'],['danger','Red']]);
  [lb,em].forEach(e=>e.addEventListener('input',upd));st.addEventListener('change',upd);
  fR(b,'Button text','',lb);fR(b,'Emoji','Optional',em);fR(b,'Color','',st);
  const fm=el('div'),draw=()=>{fm.innerHTML='';
    if(bt.form_enabled){fR(fm,'Form title','Top of the form, 45 characters max',fT(bt,'form_title',45));
      fm.append(el('h3','','Questions (Discord allows up to 5 per form)'));
      bt.questions.forEach((q,qi)=>{const qc=el('div','qcard'),t2=el('div','two'),t3=el('div','two'),tr=el('div','qrow');
        const ql=fT(q,'label',45),qp=fT(q,'placeholder',100);ql.placeholder='Question';qp.placeholder='Hint text (optional)';t2.append(ql,qp);
        t3.append(fS(q,'style',[['short','Short answer'],['paragraph','Long answer']]),fN(q,'max_length',1,4000));
        const rq=el('label','','Required');rq.prepend(fW(q,'required'));const rm=el('button','btn ghost sm','Remove');rm.onclick=()=>{bt.questions.splice(qi,1);draw();touch()};
        tr.append(rq,rm);qc.append(t2,t3,tr);fm.append(qc)});
      if(bt.questions.length<5){const ad=el('button','btn ghost sm','Add question');ad.style.margin='14px 0';ad.onclick=()=>{bt.questions.push(newQ());draw();touch()};fm.append(ad)}
    }else fR(fm,'Ticket subject','Used as the subject because no form is shown',fT(bt,'ticket_subject',100));
    fR(fm,'Message inside the ticket','Optional, replaces the panel one for this button',fA(bt,'ticket_message'),1)};
  fR(b,'Ask a form first','Turn off to open the ticket instantly',fW(bt,'form_enabled',draw));b.append(fm);draw();c.append(b);return c;
}
function panelEditor(p){
  const D=p?clone(p):newPanel(),f=$('fields');f.innerHTML='';$('secTitle').textContent=p?'Edit panel':'New panel';
  const back=el('button','btn ghost sm','Back to panels');back.onclick=()=>{if(cur().dirty()&&!confirm('Discard unsaved changes?'))return;renderPanels()};f.append(back);
  let base=p?clone(p):null,snap=JSON.stringify(D);
  const saveD=async()=>{const r=await api(`/api/guilds/${G.id}/panels/${D.id||'new'}`,PJ('PUT',D));D.id=r.id;base=clone(D);snap=JSON.stringify(D)};
  CTL={dirty:()=>JSON.stringify(D)!==snap,save:saveD,reset:()=>panelEditor(base)};touch();
  f.append(el('h3','','Panel message'));let b=el('div','sec');
  fR(b,'Panel name','Only you see this',fT(D,'name',60));fR(b,'Title','',fT(D,'embed_title',200));fR(b,'Description','',fA(D,'embed_description'),1);
  const col=el('input');col.type='color';col.value=D.embed_color;fR(b,'Color','',bindv(D,'embed_color',col));f.append(b);
  f.append(el('h3','','Tickets'));b=el('div','sec');
  fR(b,'Category','New ticket channels are created here',(()=>{const e=fS(D,'category',optsOf(META.categories,'None'));return e})());
  fR(b,'Support roles','Who can see these tickets',fC(D,'support_roles',META.roles),1);
  fR(b,'Log channel','Transcripts and events',fS(D,'log_channel',optsOf(META.channels,'None','#')));
  fR(b,'Max open per member','',fN(D,'max_open',1,10));fR(b,'Message inside new tickets','',fA(D,'ticket_message'),1);f.append(b);
  f.append(el('h3','','Buttons (up to 25)'));const bw=el('div');f.append(bw);
  const draw=()=>{bw.innerHTML='';D.buttons.forEach((bt,i)=>bw.append(btnCard(D,bt,i,draw)));
    if(D.buttons.length<25){const ad=el('button','btn ghost','Add button');ad.style.marginTop='14px';ad.onclick=()=>{D.buttons.push(newBtn());draw();touch()};bw.append(ad)}};draw();
  f.append(el('h3','','Publish'));b=el('div','sec');const chs=el('select');optsOf(META.channels,'Choose a channel','#').forEach(([a,n])=>chs.add(new Option(n,a)));chs.value=D.channel||'';
  fR(b,'Post in channel','Posting again updates the same message',chs);f.append(b);
  const out=el('div','toast'),ps=el('button','btn pri','Post to channel');
  const acts=el('div','acts');acts.style.margin='16px 0';acts.append(ps,out);f.append(acts);
  ps.onclick=async()=>{out.className='toast';out.textContent='Posting...';
    try{if(!chs.value)throw new Error('Choose a channel first');await saveD();await api(`/api/guilds/${G.id}/panels/${D.id}/post`,PJ('POST',{channel:chs.value}));
      D.channel=chs.value;base=clone(D);snap=JSON.stringify(D);out.textContent='Posted. Members can use the buttons now.';touch()}
    catch(e){out.className='toast bad';out.textContent=e.message}};
}
const SPIDER='<span class="kn">♞︎</span>';
const spl=t=>{const d=el('div','spl');d.innerHTML=`<div class="ktrack">${SPIDER}</div>`;d.append(el('small','',t||'Loading'));return d};
const skel=f=>f.append(spl('Loading'));
function showBoot(t){const b=$('boot');b.innerHTML='';b.append(spl(t));b.classList.remove('gone')}
function hideBoot(){$('boot').classList.add('gone')}
$('keep').onchange=()=>{$('dclogin').href='/auth/login?remember='+($('keep').checked?1:0)};
$('dclogin').onclick=()=>showBoot('Taking you to Discord');
function moveGlide(){const nv=$('nav');let g=nv.querySelector('.glide');if(!g){g=el('div','glide');nv.prepend(g)}const b=nv.querySelector('button.on');if(!b){g.style.opacity=0;return}g.style.opacity=1;g.style.height=b.offsetHeight+'px';g.style.transform=`translateY(${b.offsetTop}px)`}
const KW={rroles:'reaction roles button roles self roles dropdown emoji react get role',giveaways:'giveaway prize winner raffle draw reroll',invites:'invite tracker who invited join code',inviters:'invites leaderboard top inviters',leave:'goodbye leave left farewell',joinroles:'auto role join verify account age new members',automod:'spam links invites caps bad words filter punishment',welcome:'greet join leave goodbye autorole embed',leveling:'xp rank level rewards voice',moderation:'log cases ban kick mute',utility:'suggest suggestions',tickets:'ticket category support roles',panels:'ticket panel button form question',otickets:'tickets claimed open',board:'leaderboard top xp',cases:'cases warn ban mute kick history search',announce:'announcement broadcast',messages:'template embed button custom message send'};
function fsearch(){const q=$('fsearch').value.trim().toLowerCase(),r=$('fsres');r.innerHTML='';if(!q){r.classList.remove('open');return}
  const hits=TABS.filter(([k,t])=>(t+' '+(KW[k]||'')+' '+(DESC[k]||'')).toLowerCase().includes(q)).slice(0,6);
  if(!hits.length){const d=el('div','empty','No feature found');d.style.padding='14px';r.append(d)}
  hits.forEach(([k,t])=>{const b=el('button');b.append(el('span','ico',ICON[k]),el('span','',t));b.onclick=()=>{$('fsearch').value='';r.classList.remove('open');$('fs').classList.remove('open');switchTab(k)};r.append(b)});r.classList.add('open')}
$('fsearch').oninput=fsearch;$('fsearch').onkeydown=e=>{if(e.key==='Enter'){const b=$('fsres').querySelector('button');if(b)b.click()}};
addEventListener('keydown',e=>{const t=document.activeElement.tagName;if(e.key==='/'&&t!=='INPUT'&&t!=='TEXTAREA'&&t!=='SELECT'&&!$('panel').classList.contains('hide')){e.preventDefault();$('fsearch').focus()}if(e.key==='Escape'){drawer(false);$('fsres').classList.remove('open');$('fs').classList.remove('open');$('umenu').classList.remove('open');$('fsearch').blur()}});
document.addEventListener('click',e=>{if(!e.target.closest('.fs'))$('fsres').classList.remove('open');const b=e.target.closest('.btn');if(b){const r=b.getBoundingClientRect(),d=Math.max(r.width,r.height),x=el('span','ripple');x.style.cssText=`width:${d}px;height:${d}px;left:${e.clientX-r.left-d/2}px;top:${e.clientY-r.top-d/2}px`;b.append(x);setTimeout(()=>x.remove(),650)}});
document.addEventListener('pointermove',e=>{const t=e.target.closest&&e.target.closest('.srv,.stat,.pcard,.qa button,.sec,.bcard');if(t){const r=t.getBoundingClientRect();t.style.setProperty('--mx',(e.clientX-r.left)+'px');t.style.setProperty('--my',(e.clientY-r.top)+'px')}});
async function renderCases(){
  CTL=null;touch();const f=$('fields');f.innerHTML='';skel(f,4);let C;
  try{C=await api(`/api/guilds/${G.id}/cases`)}catch(e){f.innerHTML='';f.append(el('div','empty',e.message));return}
  f.innerHTML='';const q=el('input');q.type='search';q.placeholder='Search by case ID, user or reason';q.style.maxWidth='none';
  const chips=el('div','chips fl'),cnt=el('p','hint'),holder=el('div');let ft='';
  const draw=()=>{const s=q.value.trim().toLowerCase();holder.innerHTML='';
    const L=C.filter(c=>(!ft||c.type===ft)&&(!s||`${c.id} ${c.user} ${c.user_id} ${c.reason} ${c.mod}`.toLowerCase().includes(s)));
    cnt.textContent=`Found ${L.length} case${L.length===1?'':'s'}.`;
    if(!L.length){holder.append(el('div','empty','No cases match.'));return}
    const box=el('div','sec');L.slice(0,100).forEach(c=>{const r=el('div','row case'),d=el('div');
      d.append(el('label','',`#${c.id}  ${c.type.toUpperCase()}  ${c.user}`),el('small','',`${c.reason||'No reason provided'}, ${when(c.time)}`));
      r.append(el('span','dot'+(c.active?' on':'')),d,el('span','go','Open \u2192'));r.onclick=()=>caseDetail(c,renderCases);box.append(r)});holder.append(box)};
  ['All',...new Set(C.map(c=>c.type))].forEach(t=>{const l=el('label'),i=el('input');i.type='radio';i.name='ct';i.checked=t==='All';i.onchange=()=>{ft=t==='All'?'':t;draw()};l.append(i,t);chips.append(l)});
  q.oninput=draw;f.append(q,chips,cnt,holder);draw();
}
function caseDetail(c,back){
  const f=$('fields');f.innerHTML='';$('secTitle').textContent=`Case #${c.id}`;
  const bk=el('button','btn ghost sm','Back to cases'),dl=el('button','btn ghost sm','Delete case'),top=el('div','bar-top');
  bk.onclick=()=>{if(cur().dirty()&&!confirm('Discard unsaved changes?'))return;back()};
  dl.onclick=async()=>{if(!confirm('Delete this case permanently?'))return;try{await api(`/api/guilds/${G.id}/cases/${c.id}`,{method:'DELETE'});CTL=null;back()}catch(e){alert(e.message)}};
  top.append(bk,dl);f.append(top);const box=el('div','sec');box.style.marginTop='16px';
  const kv=(k,v)=>{const r=el('div','row');r.append(el('label','',k),el('span','',v));box.append(r)};
  kv('Case ID','#'+c.id);kv('Type',c.type.toUpperCase());kv('Status',c.active?'Active':'Closed');kv('User',`${c.user} (${c.user_id})`);kv('Moderator',c.mod);kv('Created',when(c.time));
  const ta=el('textarea');ta.value=c.reason;ta.maxLength=500;fR(box,'Reason','Edit it, then use the Save popup',ta,1);f.append(box);
  let saved=c.reason;CTL={dirty:()=>ta.value!==saved,save:async()=>{await api(`/api/guilds/${G.id}/cases/${c.id}`,PJ('PUT',{reason:ta.value}));c.reason=ta.value;saved=ta.value},reset:()=>caseDetail(c,back)};touch();
}
const newEmbed=()=>({title:'',description:'',color:'#c9a227',author:'',footer:'',image:'',thumbnail:'',fields:[]});
const newTpl=()=>({id:'',name:'My message',content:'',embeds:[{...newEmbed(),title:'Hello!',description:'Write your message here.'}],buttons:[],channel:'',message_id:''});
async function renderMessages(){
  CTL=null;PREV=null;touch();const f=$('fields');f.innerHTML='';$('secTitle').textContent='Messages';skel(f,3);let P;
  try{P=await api(`/api/guilds/${G.id}/templates`)}catch(e){f.innerHTML='';f.append(el('div','empty',e.message));return}
  f.innerHTML='';const top=el('div','bar-top'),nb=el('button','btn pri','Create template');nb.onclick=()=>tplEditor(null);
  top.append(el('p','hint','Templates are reusable messages with embeds and link buttons. Send them to any channel.'),nb);f.append(top);
  if(!P.length){f.append(el('div','empty','No templates yet. Create your first one.'));return}
  const grid=el('div','pgrid');
  P.forEach(p=>{const c=el('div','pcard'),a=el('div','acts'),ed=el('button','btn ghost sm','Edit'),dl=el('button','btn ghost sm','Delete');
    c.append(el('b','',p.name),el('small','',`${p.embeds.length} embed${p.embeds.length===1?'':'s'}, ${p.buttons.length} button${p.buttons.length===1?'':'s'}, ${p.message_id?'sent':'not sent yet'}`));
    ed.onclick=()=>tplEditor(p);dl.onclick=async()=>{if(!confirm('Delete this template? Messages already sent stay in Discord.'))return;try{await api(`/api/guilds/${G.id}/templates/${p.id}`,{method:'DELETE'});renderMessages()}catch(e){alert(e.message)}};
    a.append(ed,dl);c.append(a);grid.append(c)});f.append(grid);
}
function embCard(D,e,i,redraw){
  const c=el('div','bcard'),hd=el('div','bhead');hd.append(el('b','',`Embed ${i+1}`));
  if(D.embeds.length>1){const rm=el('button','btn ghost sm','Remove');rm.onclick=()=>{D.embeds.splice(i,1);redraw();touch()};hd.append(rm)}c.append(hd);
  const b=el('div','sec'),col=el('input');col.type='color';col.value=e.color;
  fR(b,'Title','',fT(e,'title',256));fR(b,'Description','',fA(e,'description'),1);fR(b,'Color','',bindv(e,'color',col));
  fR(b,'Author','Small text above the title',fT(e,'author',256));fR(b,'Footer','',fT(e,'footer',2048));
  fR(b,'Thumbnail link','https:// image, shown top right',fT(e,'thumbnail',500));fR(b,'Big image link','https:// image, shown at the bottom',fT(e,'image',500));
  const fw=el('div'),drawF=()=>{fw.innerHTML='';
    e.fields.forEach((x,k)=>{const q=el('div','qcard'),t=el('div','two'),n=fT(x,'name',256),v=fT(x,'value',1024),tr=el('div','qrow'),il=el('label','','Side by side'),rm=el('button','btn ghost sm','Remove');
      n.placeholder='Field name';v.placeholder='Field value';t.append(n,v);il.prepend(fW(x,'inline'));rm.onclick=()=>{e.fields.splice(k,1);drawF();touch()};tr.append(il,rm);q.append(t,tr);fw.append(q)});
    if(e.fields.length<10){const ad=el('button','btn ghost sm','Add field');ad.style.margin='12px 0';ad.onclick=()=>{e.fields.push({name:'',value:'',inline:false});drawF();touch()};fw.append(ad)}};
  drawF();b.append(fw);c.append(b);return c;
}
function tplEditor(p){
  const D=p?clone(p):newTpl(),f=$('fields');f.innerHTML='';$('secTitle').textContent=p?'Edit template':'New template';
  const back=el('button','btn ghost sm','Back to templates');back.onclick=()=>{if(cur().dirty()&&!confirm('Discard unsaved changes?'))return;renderMessages()};f.append(back);
  let base=p?clone(p):null,snap=JSON.stringify(D);
  const saveD=async()=>{const r=await api(`/api/guilds/${G.id}/templates/${D.id||'new'}`,PJ('PUT',D));D.id=r.id;base=clone(D);snap=JSON.stringify(D)};
  CTL={dirty:()=>JSON.stringify(D)!==snap,save:saveD,reset:()=>tplEditor(base)};
  const grid=el('div','tgrid'),L=el('div'),R=el('div','prev'),pv=el('div','dmsg');grid.append(L,R);R.append(el('h3','','Preview'),pv);f.append(grid);
  PREV=()=>{pv.innerHTML='';const hd=el('div','dhead'),im=el('img');im.src='/xypher-pfp.jpg?v=3';im.alt='';hd.append(im,el('b','','Xypher'),el('span','tag','BOT'));pv.append(hd);
    if(D.content)pv.append(el('div','dtext',D.content));
    D.embeds.forEach(e=>{const bx=el('div','emb'),bd=el('div','embody');bx.style.borderLeftColor=e.color;
      if(e.author)bd.append(el('div','eau',e.author));if(e.title)bd.append(el('div','eti',e.title));if(e.description)bd.append(el('div','ede',e.description));
      if(e.fields.length){const g=el('div','efs');e.fields.forEach(x=>{const c=el('div','ef'+(x.inline?' in':''));c.append(el('b','',x.name||'Name'),el('div','',x.value||'Value'));g.append(c)});bd.append(g)}
      if((e.image||'').startsWith('https://')){const i=el('img','eim');i.src=e.image;bd.append(i)}
      if(e.footer)bd.append(el('div','eft',e.footer));bx.append(bd);
      if((e.thumbnail||'').startsWith('https://')){const t=el('img','eth');t.src=e.thumbnail;bx.append(t)}pv.append(bx)});
    if(D.buttons.length){const r=el('div','dbtns');D.buttons.forEach(x=>r.append(el('span','dbtn secondary',`${x.emoji||''} ${x.label||'Button'} \u2197`.trim())));pv.append(r)}};
  let b=el('div','sec');fR(b,'Template name','Only you see this',fT(D,'name',60));fR(b,'Message text','Shown above the embeds',fA(D,'content'),1);L.append(el('h3','','Message'),b);
  L.append(el('h3','','Embeds (up to 3)'));const ew=el('div');L.append(ew);
  const drawE=()=>{ew.innerHTML='';D.embeds.forEach((e,i)=>ew.append(embCard(D,e,i,drawE)));
    if(D.embeds.length<3){const ad=el('button','btn ghost','Add embed');ad.style.marginTop='14px';ad.onclick=()=>{D.embeds.push(newEmbed());drawE();touch()};ew.append(ad)}};drawE();
  L.append(el('h3','','Link buttons (up to 5)'));const bw=el('div');L.append(bw);
  const drawB=()=>{bw.innerHTML='';
    D.buttons.forEach((x,i)=>{const r=el('div','qcard'),t2=el('div','two'),la=fT(x,'label',80),em=fT(x,'emoji',32),ur=fT(x,'url',500),rm=el('button','btn ghost sm','Remove');
      la.placeholder='Button text';em.placeholder='Emoji (optional)';ur.placeholder='https://...';t2.append(la,em);rm.onclick=()=>{D.buttons.splice(i,1);drawB();touch()};r.append(t2,ur,rm);bw.append(r)});
    if(D.buttons.length<5){const ad=el('button','btn ghost','Add button');ad.style.marginTop='14px';ad.onclick=()=>{D.buttons.push({label:'',url:'',emoji:''});drawB();touch()};bw.append(ad)}};drawB();
  L.append(el('h3','','Send'));b=el('div','sec');const chs=el('select');optsOf(META.channels,'Choose a channel','#').forEach(([a,n])=>chs.add(new Option(n,a)));chs.value=D.channel||'';
  fR(b,'Channel','Sending again to the same channel updates the message',chs);L.append(b);
  const out=el('div','toast'),ps=el('button','btn pri','Send message'),acts=el('div','acts');acts.style.margin='16px 0';acts.append(ps,out);L.append(acts);
  ps.onclick=async()=>{out.className='toast';out.textContent='Sending...';
    try{if(!chs.value)throw new Error('Choose a channel first');await saveD();await api(`/api/guilds/${G.id}/templates/${D.id}/send`,PJ('POST',{channel:chs.value}));
      D.channel=chs.value;base=clone(D);snap=JSON.stringify(D);out.textContent='Sent!';touch()}catch(e){out.className='toast bad';out.textContent=e.message}};
  touch();
}
const rel=t=>{const d=t*1000-Date.now(),m=Math.round(Math.abs(d)/60000),hh=Math.floor(m/60),dd=Math.floor(hh/24),x=dd?`${dd}d ${hh%24}h`:hh?`${hh}h ${m%60}m`:`${m}m`;return d>0?`in ${x}`:`${x} ago`};
async function renderGiveaways(){
  CTL=null;PREV=null;touch();const f=$('fields');f.innerHTML='';$('secTitle').textContent='Giveaways';skel(f);let L;
  try{L=await api(`/api/guilds/${G.id}/giveaways`)}catch(e){f.innerHTML='';f.append(el('div','empty',e.message));return}
  f.innerHTML='';const top=el('div','bar-top'),nb=el('button','btn pri','Start giveaway');nb.onclick=gwForm;
  top.append(el('p','hint','Members enter with a button. Xypher picks the winners when the timer ends.'),nb);f.append(top);
  if(!L.length){f.append(el('div','empty','No giveaways yet. Start your first one.'));return}
  const grid=el('div','pgrid');
  L.forEach(x=>{const c=el('div','pcard'),a=el('div','acts'),on=x.status==='active';
    c.append(el('b','',x.prize),el('small','',`${on?'Ends ':'Ended '}${rel(x.end)}`),el('small','',`${x.entries} entr${x.entries===1?'y':'ies'}, ${x.winners} winner${x.winners===1?'':'s'}, in #${x.channel}`));
    if(!on)c.append(el('small','',x.winner_names.length?'Won by '+x.winner_names.join(', '):'Nobody entered'));
    const act=(label,url,method,ask)=>{const b=el('button','btn ghost sm',label);b.onclick=async()=>{if(!confirm(ask))return;try{await api(url,{method});renderGiveaways()}catch(e){alert(e.message)}};a.append(b)};
    const base=`/api/guilds/${G.id}/giveaways/${x.id}`;
    if(on){act('End now',base+'/end','POST','End this giveaway now and pick winners?');act('Cancel',base,'DELETE','Cancel this giveaway? No winners will be picked.')}
    else{act('Reroll',base+'/reroll','POST','Pick new winners?');act('Delete',base,'DELETE','Remove this giveaway from the list?')}
    c.append(a);grid.append(c)});f.append(grid);
}
function gwForm(){
  CTL=null;PREV=null;touch();const f=$('fields');f.innerHTML='';$('secTitle').textContent='Start a giveaway';
  const D={prize:'',description:'',winners:1,dur:1,unit:'hours',channel:'',role:''},back=el('button','btn ghost sm','Back to giveaways');back.onclick=renderGiveaways;f.append(back);
  const b=el('div','sec');b.style.marginTop='16px';
  fR(b,'Prize','What the winner gets',fT(D,'prize',200));fR(b,'Description','Optional extra details',fA(D,'description'),1);fR(b,'Winners','How many people win',fN(D,'winners',1,20));
  const dr=el('div','two');dr.style.maxWidth='300px';dr.append(fN(D,'dur',1,999),fS(D,'unit',[['minutes','Minutes'],['hours','Hours'],['days','Days']]));fR(b,'Duration','Between 1 minute and 30 days',dr);
  fR(b,'Channel','Where the giveaway is posted',fS(D,'channel',optsOf(META.channels,'Choose a channel','#')));
  fR(b,'Required role','Optional. Only members with this role can enter',fS(D,'role',optsOf(META.roles,'Anyone can enter')));f.append(b);
  const out=el('div','toast'),go=el('button','btn pri','Start giveaway'),acts=el('div','acts');acts.style.margin='16px 0';acts.append(go,out);f.append(acts);
  go.onclick=async()=>{out.className='toast';out.textContent='Starting...';
    try{if(!D.prize.trim())throw new Error('Write the prize first');if(!D.channel)throw new Error('Choose a channel');await api(`/api/guilds/${G.id}/giveaways`,PJ('POST',D));renderGiveaways()}
    catch(e){out.className='toast bad';out.textContent=e.message}};
}
async function renderInviters(){
  CTL=null;PREV=null;touch();const f=$('fields');f.innerHTML='';$('secTitle').textContent='Top inviters';skel(f);let L;
  try{L=await api(`/api/guilds/${G.id}/inviters`)}catch(e){f.innerHTML='';f.append(el('div','empty',e.message));return}
  f.innerHTML='';if(!L.length){f.append(el('div','empty','No invites tracked yet. Turn on the Invite tracker and new members will be counted.'));return}
  const top=Math.max(1,L[0].invites),box=el('div','sec');
  L.forEach((u,i)=>{const r=el('div','row'),d=el('div'),m=el('div','meter');d.append(el('label','',`${i+1}. ${u.name}`),el('small','',`${u.invites} invites (${u.total} joined, ${u.left} left)`));
    m.append(el('i'));m.firstChild.style.setProperty('--w',Math.max(4,u.invites/top*100)+'%');r.append(d,m);box.append(r)});f.append(box);
}
function tplPrev(t){
  const S={'{user}':'@Peter','{inviter}':'@Mary','{code}':'x7Kp2','{invites}':'12','{count}':'248','{server}':'Xypher HQ'};
  const sb=x=>Object.entries(S).reduce((a,[k,v])=>a.split(k).join(v),(x||'').replace(/\*\*/g,'').replace(/`/g,''));
  const d=el('div','dmsg mini'),bx=el('div','emb'),bd=el('div','embody');bx.style.borderLeftColor=t.color;
  if(t.author)bd.append(el('div','eau',sb(t.author)));if(t.title)bd.append(el('div','eti',sb(t.title)));if(t.desc)bd.append(el('div','ede',sb(t.desc)));
  if(t.fields.length){const g=el('div','efs');t.fields.forEach(([n,v])=>{const c=el('div','ef in');c.append(el('b','',sb(n)),el('div','',sb(v)));g.append(c)});bd.append(g)}
  if(t.footer)bd.append(el('div','eft',sb(t.footer)));bx.append(bd);if(t.thumb)bx.append(el('div','eth fake','P'));d.append(bx);return d}
const newItem=()=>({emoji:'',label:'',role:'',description:''});
const newRR=()=>({id:'',name:'Roles',mode:'buttons',title:'Pick your roles',description:'Tap a button below to get or remove a role.',color:'#c9a227',unique:false,items:[newItem()],channel:'',message_id:''});
const RRMODE={buttons:'Buttons',dropdown:'Dropdown menu',reactions:'Emoji reactions'};
async function renderRR(){
  CTL=null;PREV=null;touch();const f=$('fields');f.innerHTML='';$('secTitle').textContent='Reaction roles';skel(f);let P;
  try{P=await api(`/api/guilds/${G.id}/rroles`)}catch(e){f.innerHTML='';f.append(el('div','empty',e.message));return}
  f.innerHTML='';const top=el('div','bar-top'),nb=el('button','btn pri','New role panel');nb.onclick=()=>rrEditor(null);
  top.append(el('p','hint','Post a message where members pick their own roles. Choose buttons, a dropdown menu or emoji reactions.'),nb);f.append(top);
  if(!P.length){f.append(el('div','empty','No role panels yet. Create your first one.'));return}
  const grid=el('div','pgrid');
  P.forEach(p=>{const c=el('div','pcard'),a=el('div','acts'),ed=el('button','btn ghost sm','Edit'),dl=el('button','btn ghost sm','Delete');
    c.append(el('b','',p.name),el('small','',`${p.items.length} role${p.items.length===1?'':'s'}, ${RRMODE[p.mode]}, ${p.message_id?'posted':'not posted yet'}`));
    ed.onclick=()=>rrEditor(p);dl.onclick=async()=>{if(!confirm('Delete this panel and its message?'))return;try{await api(`/api/guilds/${G.id}/rroles/${p.id}`,{method:'DELETE'});renderRR()}catch(e){alert(e.message)}};
    a.append(ed,dl);c.append(a);grid.append(c)});f.append(grid);
}
function rrEditor(p){
  const D=p?clone(p):newRR(),f=$('fields');f.innerHTML='';$('secTitle').textContent=p?'Edit role panel':'New role panel';
  const back=el('button','btn ghost sm','Back to list');back.onclick=()=>{if(cur().dirty()&&!confirm('Discard unsaved changes?'))return;renderRR()};f.append(back);
  let base=p?clone(p):null,snap=JSON.stringify(D);
  const saveD=async()=>{const r=await api(`/api/guilds/${G.id}/rroles/${D.id||'new'}`,PJ('PUT',D));D.id=r.id;base=clone(D);snap=JSON.stringify(D)};
  CTL={dirty:()=>JSON.stringify(D)!==snap,save:saveD,reset:()=>rrEditor(base)};
  const grid=el('div','tgrid'),L=el('div'),R=el('div','prev'),pv=el('div','dmsg');grid.append(L,R);R.append(el('h3','','Preview'),pv);f.append(grid);
  const roleName=id=>(META.roles.find(r=>r.id===id)||{}).name||'Role';
  PREV=()=>{pv.innerHTML='';const hd=el('div','dhead'),im=el('img');im.src='/xypher-pfp.jpg?v=3';im.alt='';hd.append(im,el('b','','Xypher'),el('span','tag','BOT'));pv.append(hd);
    const bx=el('div','emb'),bd=el('div','embody');bx.style.borderLeftColor=D.color;if(D.title)bd.append(el('div','eti',D.title));if(D.description)bd.append(el('div','ede',D.description));bx.append(bd);pv.append(bx);
    if(D.mode==='dropdown')pv.append(el('div','selmock','Choose your roles...  \u25be'));
    else{const r=el('div','dbtns');D.items.forEach(x=>r.append(el('span',D.mode==='buttons'?'dbtn secondary':'rx',D.mode==='buttons'?`${x.emoji||''} ${x.label||(x.emoji?'':roleName(x.role))}`.trim():(x.emoji||'?'))));pv.append(r)}};
  PREV();
  const hints={buttons:'Each role gets its own button. Tap to get the role, tap again to remove it.',dropdown:'One menu where members tick the roles they want.',reactions:'Members react to the message with an emoji to get the role.'};
  let b=el('div','sec');const col=el('input'),ms=fS(D,'mode',Object.entries(RRMODE)),hint=el('small','',hints[D.mode]);col.type='color';col.value=D.color;
  fR(b,'Panel name','Only you see this',fT(D,'name',60));fR(b,'Style','',ms);b.append(hint);
  fR(b,'One role at a time','Picking a new role removes the other roles from this panel',fW(D,'unique'));
  fR(b,'Title','',fT(D,'title',200));fR(b,'Description','',fA(D,'description'),1);fR(b,'Color','',bindv(D,'color',col));L.append(el('h3','','Message'),b);
  L.append(el('h3','','Roles'));const iw=el('div');L.append(iw);
  const drawI=()=>{iw.innerHTML='';hint.textContent=hints[D.mode];
    D.items.forEach((x,i)=>{const c=el('div','qcard'),t2=el('div','two'),em=fT(x,'emoji',64),lb=fT(x,'label',80),rs=fS(x,'role',optsOf(META.roles,'Choose a role'));
      em.placeholder='Emoji';lb.placeholder=D.mode==='reactions'?'Name (optional)':D.mode==='dropdown'?'Option text':'Button text (empty = emoji only)';t2.append(em,lb);c.append(t2,rs);
      if(D.mode==='dropdown'){const ds=fT(x,'description',100);ds.placeholder='Short description (optional)';c.append(ds)}
      if(D.items.length>1){const rm=el('button','btn ghost sm','Remove');rm.onclick=()=>{D.items.splice(i,1);drawI();touch()};c.append(rm)}iw.append(c)});
    if(D.items.length<(D.mode==='reactions'?20:25)){const ad=el('button','btn ghost','Add role');ad.style.marginTop='14px';ad.onclick=()=>{D.items.push(newItem());drawI();touch()};iw.append(ad)}};
  ms.addEventListener('change',drawI);drawI();
  L.append(el('h3','','Post'));b=el('div','sec');const chs=el('select');optsOf(META.channels,'Choose a channel','#').forEach(([a,n])=>chs.add(new Option(n,a)));chs.value=D.channel||'';
  fR(b,'Channel','Posting again updates the same message',chs);L.append(b);
  const out=el('div','toast'),ps=el('button','btn pri','Post to channel'),acts=el('div','acts');acts.style.margin='16px 0';acts.append(ps,out);L.append(acts);
  ps.onclick=async()=>{out.className='toast';out.textContent='Posting...';
    try{if(!chs.value)throw new Error('Choose a channel first');await saveD();await api(`/api/guilds/${G.id}/rroles/${D.id}/post`,PJ('POST',{channel:chs.value}));
      D.channel=chs.value;base=clone(D);snap=JSON.stringify(D);out.textContent='Posted. Members can pick their roles now.';touch()}catch(e){out.className='toast bad';out.textContent=e.message}};
  touch();
}
function crestSvg(c){const n='http://www.w3.org/2000/svg',s=document.createElementNS(n,'svg');s.setAttribute('viewBox','0 0 400 400');if(c)s.setAttribute('class',c);
  const A=[0,18,36,54,72,90].map(a=>a*Math.PI/180);let d='';A.forEach(a=>d+=`M0 0L${400*Math.cos(a)} ${400*Math.sin(a)}`);
  for(let r=60;r<=400;r+=65){d+=`M${r} 0A${r} ${r} 0 0 1 0 ${r}`}
  const p=document.createElementNS(n,'path');p.setAttribute('d',d);s.append(p);return s}
$('login').prepend(crestSvg(),crestSvg('r'));document.body.append(crestSvg('bgcrest'));
$('avb').onclick=e=>{e.stopPropagation();$('umenu').classList.toggle('open')};
$('fsbtn').onclick=e=>{e.stopPropagation();const f=$('fs');f.classList.toggle('open');if(f.classList.contains('open'))setTimeout(()=>$('fsearch').focus(),60)};
document.addEventListener('click',e=>{if(!e.target.closest('.um'))$('umenu').classList.remove('open');if(!e.target.closest('.fs,#fsbtn'))$('fs').classList.remove('open')});
$('menubtn').onclick=()=>drawer(true);$('scrim').onclick=()=>drawer(false);
addEventListener('resize',()=>{if(innerWidth>720)drawer(false)});
let tx=0,ty=0;addEventListener('touchstart',e=>{tx=e.touches[0].clientX;ty=e.touches[0].clientY},{passive:true});
addEventListener('touchend',e=>{const dx=e.changedTouches[0].clientX-tx,dy=e.changedTouches[0].clientY-ty;if(dx<-60&&Math.abs(dy)<Math.abs(dx)*.6)drawer(false)},{passive:true});
const setHH=()=>{const hd=document.querySelector('#app>header');if(hd)document.documentElement.style.setProperty('--hh',hd.offsetHeight+'px')};
addEventListener('resize',setHH);new ResizeObserver(setHH).observe(document.querySelector('#app>header'));
showBoot('Waking Xypher up');init0().catch(()=>{}).finally(()=>setTimeout(hideBoot,300));
</script></body></html>
'''


# ================= giveaways (bot side) =================
_GF, _IF = "giveaways.json", "invites.json"
def _jl(path):
    try:
        with open(path, encoding="utf8") as f: return json.load(f)
    except (FileNotFoundError, ValueError): return {}
def _js(path, d):
    with open(path, "w", encoding="utf8") as f: json.dump(d, f)

class GwView(discord.ui.View):
    def __init__(self, cog, k):
        super().__init__(timeout=None)
        b = discord.ui.Button(style=discord.ButtonStyle.primary, label="Enter", emoji="\U0001F389", custom_id=f"gw:{k}")
        async def cb(it): await cog.enter(it, k)
        b.callback = cb; self.add_item(b)

class Giveaways(commands.Cog):
    def __init__(self, bot): self.bot, self.data, self.dirty = bot, _jl(_GF), set()
    def g(self, guild_id): return self.data.setdefault(str(guild_id), {})
    def save(self): _js(_GF, self.data)

    async def cog_load(self):
        for items in self.data.values():
            for k, d in items.items():
                if d["status"] == "active" and d.get("message_id"): self.bot.add_view(GwView(self, k), message_id=int(d["message_id"]))
        self.loop.start()
    async def cog_unload(self): self.loop.cancel()

    def embed(self, d):
        ended, e = d["status"] != "active", discord.Embed(title="\U0001F389 " + d["prize"], color=0x2B2D31 if d["status"] != "active" else 0xE0222D)
        t = (d.get("description") or "") + ("\n\n" if d.get("description") else "")
        if ended:
            w = d.get("winners_ids", [])
            t += "**Winners:** " + (", ".join(f"<@{x}>" for x in w) if w else "No valid entries") + f"\n**Ended:** <t:{int(d['end'])}:R>"
        else:
            t += f"**Ends:** <t:{int(d['end'])}:R> (<t:{int(d['end'])}:f>)\n**Winners:** {d['winners']}"
            if d.get("role"): t += f"\n**Requires:** <@&{d['role']}>"
        e.description = t + f"\n**Hosted by:** <@{d['host_id']}>"
        e.set_footer(text=f"{len(d['entries'])} entries" + (" | Ended" if ended else ""))
        return e

    async def start(self, guild, ch, host_id, prize, desc, winners, seconds, role):
        k = secrets.token_hex(4)
        d = {"id": k, "channel": ch.id, "message_id": 0, "prize": prize, "description": desc, "winners": winners, "end": time.time() + seconds,
             "host_id": host_id, "role": role, "status": "active", "entries": [], "winners_ids": []}
        msg = await ch.send(embed=self.embed(d), view=GwView(self, k))
        d["message_id"] = msg.id; self.g(guild.id)[k] = d; self.save()
        return k

    async def enter(self, it, k):
        d = self.g(it.guild_id).get(k)
        if not d or d["status"] != "active" or time.time() >= d["end"]:
            return await it.response.send_message("This giveaway has ended.", ephemeral=True)
        if d.get("role") and not any(r.id == int(d["role"]) for r in it.user.roles):
            return await it.response.send_message(f"You need the <@&{d['role']}> role to enter.", ephemeral=True)
        if it.user.id in d["entries"]: d["entries"].remove(it.user.id); txt = "You left the giveaway."
        else: d["entries"].append(it.user.id); txt = "You're in! Good luck \U0001F340"
        self.save(); self.dirty.add((it.guild_id, k))
        await it.response.send_message(txt, ephemeral=True)

    async def finish(self, guild_id, k, reroll=False):
        d, guild = self.g(guild_id).get(k), self.bot.get_guild(int(guild_id))
        if not d or not guild: return
        pool = [u for u in d["entries"] if (m := guild.get_member(u)) and not m.bot]
        d["winners_ids"] = random.sample(pool, min(d["winners"], len(pool)))
        d["status"] = "ended"
        if not reroll: d["end"] = min(d["end"], time.time())
        self.save()
        ch, msg = guild.get_channel(int(d["channel"])), None
        if not ch: return
        try: msg = await ch.fetch_message(int(d["message_id"])); await msg.edit(embed=self.embed(d), view=None)
        except discord.HTTPException: pass
        win = ", ".join(f"<@{x}>" for x in d["winners_ids"])
        txt = (f"\U0001F389 {'New winner(s): ' if reroll else 'Congratulations '}{win}! You won **{d['prize']}**" if win else f"No valid entries for **{d['prize']}**, so nobody won.")
        try:
            if msg: await ch.send(txt, reference=msg)
            else: await ch.send(txt)
        except discord.HTTPException: pass
        for x in d["winners_ids"]:      # DM every winner
            try:
                m = guild.get_member(int(x))
                if m: await safe_dm(m, "You won! \U0001F389", f"**Server:** {guild.name}\n**Prize:** {d['prize']}", BLUE)
            except Exception: pass

    @tasks.loop(seconds=15)
    async def loop(self):
        now = time.time()
        for gid, items in list(self.data.items()):
            for k, d in list(items.items()):
                if d["status"] != "active": continue
                if d["end"] <= now: await self.finish(gid, k)
                elif (int(gid), k) in self.dirty:
                    self.dirty.discard((int(gid), k)); guild = self.bot.get_guild(int(gid)); ch = guild.get_channel(int(d["channel"])) if guild else None
                    try: msg = await ch.fetch_message(int(d["message_id"])); await msg.edit(embed=self.embed(d))
                    except (discord.HTTPException, AttributeError): pass
    @loop.before_loop
    async def _wait(self): await self.bot.wait_until_ready()

# ================= invite tracker (bot side) =================
class InviteTracker(commands.Cog):
    DEF = {"enabled": False, "channel": None, "template": "classic"}
    def __init__(self, bot): self.bot, self.data, self.cache = bot, _jl(_IF), {}
    def guild(self, gid):
        g = self.data.setdefault(str(gid), {})
        for k in ("cfg", "joins", "counts"): g.setdefault(k, {})
        return g
    def cfg(self, gid):
        c = self.guild(gid)["cfg"]
        for k, v in self.DEF.items(): c.setdefault(k, v)
        return c
    def save(self): _js(_IF, self.data)
    def total(self, gid, uid):
        c = self.guild(gid)["counts"].get(str(uid), {"total": 0, "left": 0}); return c["total"] - c["left"]

    async def snap(self, guild):
        try: self.cache[guild.id] = {i.code: (i.uses or 0) for i in await guild.invites()}
        except discord.HTTPException: self.cache.pop(guild.id, None)
    @commands.Cog.listener()
    async def on_ready(self):
        for g in self.bot.guilds: await self.snap(g)
    @commands.Cog.listener()
    async def on_guild_join(self, guild): await self.snap(guild)
    @commands.Cog.listener()
    async def on_invite_create(self, inv): self.cache.setdefault(inv.guild.id, {})[inv.code] = inv.uses or 0
    @commands.Cog.listener()
    async def on_invite_delete(self, inv): self.cache.get(inv.guild.id, {}).pop(inv.code, None)

    def fmt(self, tpl, m, inviter=None, code=None):
        return (tpl.replace("{user}", m.mention).replace("{inviter}", f"<@{inviter}>" if inviter else "Unknown").replace("{code}", code or "unknown")
                   .replace("{invites}", str(self.total(m.guild.id, inviter)) if inviter else "0").replace("{count}", str(m.guild.member_count)).replace("{server}", m.guild.name))
    def build(self, tid, m, inviter, code):
        t, f = next((x for x in INV_TPLS if x["id"] == tid), INV_TPLS[0]), (lambda x: self.fmt(x, m, inviter, code))
        e = discord.Embed(title=f(t["title"]) or None, description=f(t["desc"]) or None, color=int(t["color"].lstrip("#"), 16))
        if t["author"]: e.set_author(name=f(t["author"]), icon_url=m.display_avatar.url)
        for n, v in t["fields"]: e.add_field(name=f(n), value=f(v), inline=True)
        if t["footer"]: e.set_footer(text=f(t["footer"]))
        if t["thumb"]: e.set_thumbnail(url=m.display_avatar.url)
        return e

    @commands.Cog.listener()
    async def on_member_join(self, m):
        if m.bot: return
        used, old = None, self.cache.get(m.guild.id)
        try:
            now = {i.code: i for i in await m.guild.invites()}
            if old is not None: used = next((i for c, i in now.items() if (i.uses or 0) > old.get(c, 0)), None)
            self.cache[m.guild.id] = {c: (i.uses or 0) for c, i in now.items()}
        except discord.HTTPException: pass
        inviter = used.inviter.id if used and used.inviter else None
        g = self.guild(m.guild.id); g["joins"][str(m.id)] = {"inviter": inviter, "code": used.code if used else None}
        if inviter: g["counts"].setdefault(str(inviter), {"total": 0, "left": 0})["total"] += 1
        self.save()
        c = self.cfg(m.guild.id); ch = m.guild.get_channel(int(c["channel"])) if c["channel"] else None
        if c["enabled"] and ch:
            try: await ch.send(embed=self.build(c["template"], m, inviter, used.code if used else None), allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException: pass
    @commands.Cog.listener()
    async def on_member_remove(self, m):
        if m.bot: return
        g = self.guild(m.guild.id); j = g["joins"].pop(str(m.id), None)
        if j and j["inviter"]: g["counts"].setdefault(str(j["inviter"]), {"total": 0, "left": 0})["left"] += 1
        self.save()

    @app_commands.command(name="invites", description="See how many people someone has invited")
    @app_commands.guild_only()
    async def invites(self, it: discord.Interaction, member: Optional[discord.Member] = None):
        m = member or it.user; c = self.guild(it.guild_id)["counts"].get(str(m.id), {"total": 0, "left": 0})
        await it.response.send_message(f"**{m.display_name}** has **{c['total'] - c['left']}** invites ({c['total']} joined, {c['left']} left).")

# ================= reaction roles (bot side) =================
_RF = "reactionroles.json"
def _norm(e): return str(e).replace("\ufe0f", "").strip()

class RRButtons(discord.ui.View):
    def __init__(self, cog, pid, p):
        super().__init__(timeout=None)
        for i, it in enumerate(p["items"]):
            b = discord.ui.Button(style=discord.ButtonStyle.secondary, label=it["label"] or None, emoji=it["emoji"] or None, custom_id=f"rr:{pid}:{i}", row=i // 5)
            async def cb(inter, i=i): await cog.toggle(inter, pid, i)
            b.callback = cb; self.add_item(b)

class RRSelect(discord.ui.View):
    def __init__(self, cog, pid, p):
        super().__init__(timeout=None)
        opts = [discord.SelectOption(label=(it["label"] or "Role")[:100], value=str(i), emoji=it["emoji"] or None, description=it.get("description") or None) for i, it in enumerate(p["items"])]
        sel = discord.ui.Select(custom_id=f"rr:{pid}:menu", placeholder="Choose your roles...", min_values=0, max_values=1 if p["unique"] else len(opts), options=opts)
        async def cb(inter): await cog.menu(inter, pid, sel.values)
        sel.callback = cb; self.add_item(sel)

class ReactionRoles(commands.Cog):
    def __init__(self, bot): self.bot, self.data = bot, _jl(_RF)
    def g(self, guild_id): return self.data.setdefault(str(guild_id), {})
    def save(self): _js(_RF, self.data)

    def message(self, pid, p):
        from theme import knight_embed
        e = knight_embed(p["title"], p["description"], int(p["color"].lstrip("#"), 16))
        return e, (RRButtons(self, pid, p) if p["mode"] == "buttons" else RRSelect(self, pid, p) if p["mode"] == "dropdown" else None)

    async def cog_load(self):
        for items in self.data.values():
            for pid, p in items.items():
                if p.get("message_id") and p["mode"] != "reactions": self.bot.add_view(self.message(pid, p)[1], message_id=int(p["message_id"]))

    async def publish(self, g, pid, p, ch):
        e, v = self.message(pid, p); msg = None
        if p.get("message_id") and p.get("channel") == ch.id:
            try: msg = await ch.fetch_message(int(p["message_id"])); await msg.edit(embed=e, view=v)
            except discord.NotFound: msg = None
        if msg is None: msg = await (ch.send(embed=e, view=v) if v else ch.send(embed=e))
        if p["mode"] == "reactions":
            try: await msg.clear_reactions()
            except discord.HTTPException: pass
            for it in p["items"]:
                try: await msg.add_reaction(it["emoji"])
                except discord.HTTPException: pass
        p["channel"], p["message_id"] = ch.id, msg.id; self.save()

    def panel_roles(self, guild, p): return [r for r in (guild.get_role(int(x["role"])) for x in p["items"]) if r]

    async def toggle(self, it, pid, i):
        await it.response.defer(ephemeral=True)
        p = self.g(it.guild_id).get(pid)
        role = it.guild.get_role(int(p["items"][i]["role"])) if p else None
        if not role: return await it.followup.send("That role no longer exists.", ephemeral=True)
        try:
            if role in it.user.roles: await it.user.remove_roles(role, reason="Reaction roles"); txt = f"Removed {role.mention}"
            else:
                if p["unique"]:
                    others = [r for r in self.panel_roles(it.guild, p) if r in it.user.roles and r != role]
                    if others: await it.user.remove_roles(*others, reason="Reaction roles")
                await it.user.add_roles(role, reason="Reaction roles"); txt = f"You now have {role.mention}"
        except discord.HTTPException: txt = "I can't manage that role. Ask an admin to move my role above it."
        await it.followup.send(txt, ephemeral=True)

    async def menu(self, it, pid, values):
        await it.response.defer(ephemeral=True)
        p = self.g(it.guild_id).get(pid)
        if not p: return await it.followup.send("This panel was removed.", ephemeral=True)
        chosen = {int(p["items"][int(v)]["role"]) for v in values}; allr = self.panel_roles(it.guild, p)
        add = [r for r in allr if r.id in chosen and r not in it.user.roles]; rem = [r for r in allr if r.id not in chosen and r in it.user.roles]
        try:
            if add: await it.user.add_roles(*add, reason="Reaction roles")
            if rem: await it.user.remove_roles(*rem, reason="Reaction roles")
            txt = "Your roles are updated."
        except discord.HTTPException: txt = "I can't manage one of those roles. Ask an admin to move my role higher."
        await it.followup.send(txt, ephemeral=True)

    async def react(self, pl, add):
        if not pl.guild_id or pl.user_id == self.bot.user.id: return
        p = next((x for x in self.g(pl.guild_id).values() if x["mode"] == "reactions" and str(x.get("message_id")) == str(pl.message_id)), None)
        item = next((x for x in p["items"] if _norm(x["emoji"]) == _norm(pl.emoji)), None) if p else None
        guild = self.bot.get_guild(pl.guild_id)
        if not item or not guild: return
        member, role = (pl.member if add and pl.member else guild.get_member(pl.user_id)), guild.get_role(int(item["role"]))
        if not member or not role or member.bot: return
        try:
            if add:
                if p["unique"]:
                    others = [r for r in self.panel_roles(guild, p) if r in member.roles and r != role]
                    if others: await member.remove_roles(*others, reason="Reaction roles")
                await member.add_roles(role, reason="Reaction roles")
            else: await member.remove_roles(role, reason="Reaction roles")
        except discord.HTTPException: pass
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, pl): await self.react(pl, True)
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, pl): await self.react(pl, False)

# ================= bot extension =================

class Dashboard(commands.Cog):
    def __init__(self, bot): self.bot, self.runner = bot, None
    async def cog_load(self): self.runner = await start_server(self.bot)
    async def cog_unload(self):
        if self.runner: await self.runner.cleanup()

async def setup(bot):
    await bot.add_cog(Giveaways(bot)); await bot.add_cog(InviteTracker(bot)); await bot.add_cog(ReactionRoles(bot)); await bot.add_cog(Dashboard(bot))
