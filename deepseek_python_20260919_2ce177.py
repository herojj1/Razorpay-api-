#!/usr/bin/env python3
# =============================================================================
# NOXNI v2.2 — CC Scraper & Cleaner Bot
# Part 1/2 — Config, helpers, fake data, all commands
# =============================================================================

import os, re, io, csv, json, math, time, random, string, asyncio
import logging
from datetime import datetime, timedelta
from collections import Counter

import aiohttp
import aiofiles
from telethon import TelegramClient, events, Button
from telethon.errors import FloodWaitError
from telethon.extensions import html as thtml

import bin_lookup
import fake_data


# ───────────── CONFIG ─────────────
API_ID    = int(os.getenv("API_ID") or 33657928)
API_HASH  = os.getenv("API_HASH", "a61fde61442113b9a65c699f7020d59a")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID  = json.loads(os.getenv("ADMIN_ID", "[8871910561]"))
CHANNEL_ID = int(os.getenv("UPLOAD_CHANNEL_ID", "-1003965573664"))

MAX_FILE_MB = 50
MAX_CARDS   = 500_000

STORAGE_DIR = "storage"
os.makedirs(STORAGE_DIR, exist_ok=True)


# ───────────── LOGGING ─────────────
log = logging.getLogger("NOXNI")
log.setLevel(logging.INFO)
_fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                          datefmt='%Y-%m-%d %H:%M:%S')
_ch = logging.StreamHandler()
_ch.setFormatter(_fmt)
log.addHandler(_ch)


def log_system(tag, msg, level="info"):
    getattr(log, level, log.info)(f"[{tag}] {msg}")


# ───────────── BOLD SANS ─────────────
_BOLD = {}
for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _BOLD[c] = "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭"[i]
for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _BOLD[c] = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇"[i]
for i, c in enumerate("0123456789"):
    _BOLD[c] = "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"[i]


def bs(t):
    if not t:
        return t
    return "".join(_BOLD.get(c, c) for c in str(t))


SEP = "━━━━━━━━━━━━━━━━━━━━"
PE  = "💎"


# ───────────── PREMIUM EMOJI IDs ─────────────
# Telegram premium (animated) emoji IDs
PREMIUM_EMOJI_IDS = {
    "✅": "5278327121008167894",
    "❌": "5785177332595561481",
    "⚠️": "5420323339723881652",
    "⚡": "6174996123522959140",
    "🔥": "5039644681583985437",
    "💎": "5427168083074628963",
    "✔️": "5206607081334906820",
    "✨": "5040016479722931047",
    "🎉": "5039778134807806727",
    "🎯": "5039905162760553480",
    "💰": "5039789890133296083",
    "💳": "5447453226498552490",
    "💲": "5447579253723918909",
    "💵": "5409048419211682843",
    "💸": "5837027045376271166",
    "🏦": "6089185885289454318",
    "📊": "5042290883949495533",
    "📈": "5039808285478224750",
    "🥇": "6179279816529814743",
    "🥈": "5042036407137207122",
    "🥉": "5039808285478224750",
    "🥔": "5039928501612839813",
    "🧨": "5039778134807806727",
    "🏆": "6089185885289454318",
    "👑": "5039727497143387500",
    "👤": "5992129361090711368",
    "🤖": "6174896506051495705",
    "⚙️": "5445059250382469069",
    "🌐": "6321225560789877992",
    "ℹ️": "5334544901428229844",
    "📍": "5391032818111363540",
    "🔑": "5399885604701880145",
    "🔒": "5445059250382469069",
    "🔓": "5445373981290952548",
    "🔗": "5042101437237036298",
    "🔐": "5445059250382469069",
    "⏰": "5445350406215465190",
    "⏱️": "5445350406215465190",
    "🚀": "6174445826543191998",
    "⭐": "5042061201983407048",
    "💫": "5042200814190330758",
    "💠": "5427168083074628963",
    "🌍": "5447410659077661506",
    "📧": "5443127283898405358",
    "💀": "5042209657527993345",
    "💯": "5042297717242463211",
    "🚫": "5039671744172917707",
    "😈": "6336664426325740768",
    "📝": "5444889156792646660",
    "📁": "6026239398650056451",
    "🗑": "5039614900280754969",
    "📅": "6168242008277125889",
    "📤": "5445355530111437729",
    "📥": "5443127283898405358",
    "🟢": "5039928501612839813",
    "🔴": "5042042652019655612",
    "🟡": "5042036407137207122",
    "🔵": "5042290883949495533",
    "⚪": "5042061201983407048",
    "⚫": "5042209657527993345",
    "📌": "5397782960512444700",
    "📋": "5445260044398524944",
    "🔍": "5042302287087666158",
    "💻": "5039579582764680065",
    "💬": "5040036030414062506",
    "📢": "5447644880824181073",
    "💡": "5042264341051605743",
    "🛒": "5445224894386172410",
    "📦": "6026239398650056451",
    "🏠": "5416041192905265756",
    "🏙️": "5447410659077661506",
    "📞": "5443127283898405358",
    "📮": "5444889156792646660",
    "🗺️": "6321225560789877992",
    "🔙": "5445365692004071819",
    "🎬": "5445355530111437729",
    "🏓": "5042200814190330758",
    "🎁": "5039778134807806727",
    "👥": "5443038326535759644",
}


def pe(text):
    """Replace emoji with premium animated emoji tags."""
    if not text:
        return text
    out = text
    for emoji in sorted(PREMIUM_EMOJI_IDS.keys(), key=len, reverse=True):
        doc_id = PREMIUM_EMOJI_IDS[emoji]
        out = out.replace(emoji, f'<tg-emoji emoji-id="{doc_id}">{emoji}</tg-emoji>')
    return out


# ───────────── CLIENT ─────────────
client = TelegramClient("noxni_bot", API_ID, API_HASH)
client_instance = client


# ───────────── MESSAGE HELPERS ─────────────
def build_entities(html_text):
    text, entities = thtml.parse(html_text)
    return text, sorted(entities, key=lambda e: e.offset)


async def styled_reply(event, html_text, buttons=None, file=None):
    try:
        text, entities = build_entities(html_text)
        return await event.reply(text, formatting_entities=entities,
                                 buttons=buttons, file=file, link_preview=False)
    except Exception as e:
        log_system("MSG", f"reply failed: {e!r}", "error")
        try:
            return await event.reply(html_text[:4000], parse_mode='html')
        except Exception:
            return None


async def styled_edit(msg, html_text, buttons=None):
    try:
        text, entities = build_entities(html_text)
        await msg.edit(text, formatting_entities=entities, buttons=buttons,
                       link_preview=False)
    except Exception:
        pass


async def styled_send(chat_id, html_text, buttons=None, file=None):
    try:
        text, entities = build_entities(html_text)
        return await client_instance.send_message(
            chat_id, text, formatting_entities=entities,
            buttons=buttons, file=file, link_preview=False)
    except Exception as e:
        log_system("MSG", f"send failed: {e!r}", "error")
        return None


def pbtn(text, data=None, url=None, style=None):
    if url:
        try:
            return Button.url(text, url, style=style)
        except TypeError:
            return Button.url(text, url)
    if data:
        payload = data.encode() if isinstance(data, str) else data
        try:
            return Button.inline(text, payload, style=style)
        except TypeError:
            return Button.inline(text, payload)
    return Button.inline(text, b"none")


def fmt_n(n):
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


# ───────────── CARD PARSING ─────────────
_CC_RE = re.compile(r'(\d{13,19})[^\d]+(\d{1,2})[^\d]+(\d{2,4})[^\d]+(\d{3,4})')


def extract_cards(text: str) -> list:
    if not text:
        return []
    out = []
    for c, m, y, cv in _CC_RE.findall(text):
        if len(y) == 2:
            y = "20" + y
        try:
            mi = int(m); yi = int(y)
            if not (1 <= mi <= 12): continue
            if not (2020 <= yi <= 2099): continue
        except Exception:
            continue
        if len(cv) not in (3, 4):
            continue
        out.append(f"{c}|{m.zfill(2)}|{y}|{cv}")
    return list(dict.fromkeys(out))


def parse_card_line(line: str):
    parts = re.split(r'[|/\\:\s]+', line.strip())
    if len(parts) < 4:
        return None
    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    if not cc.isdigit() or not (13 <= len(cc) <= 19):
        return None
    if not mm.isdigit() or not (1 <= int(mm) <= 12):
        return None
    if not yy.isdigit():
        return None
    if len(yy) == 2:
        yy = "20" + yy
    if not (2020 <= int(yy) <= 2099):
        return None
    if not cvv.isdigit() or len(cvv) not in (3, 4):
        return None
    return (cc, mm.zfill(2), yy, cvv)


def is_expired(mm, yyyy):
    try:
        m, y = int(mm), int(yyyy)
        now = datetime.now()
        return (y < now.year) or (y == now.year and m < now.month)
    except Exception:
        return True


def luhn_ok(number):
    try:
        digits = [int(d) for d in number if d.isdigit()]
    except ValueError:
        return False
    if len(digits) < 12:
        return False
    csum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        csum += d
    return csum % 10 == 0


def detect_brand(cc):
    if cc.startswith("4"): return "Visa"
    if re.match(r'^5[1-5]', cc) or re.match(r'^2[2-7]', cc): return "MasterCard"
    if re.match(r'^3[47]', cc): return "Amex"
    if re.match(r'^6(?:011|5)', cc): return "Discover"
    if re.match(r'^35', cc): return "JCB"
    if re.match(r'^62', cc): return "UnionPay"
    if re.match(r'^3(?:0[0-5]|[68])', cc): return "Diners"
    if re.match(r'^(50|56|57|58|63|67|6[0-9])', cc): return "Maestro"
    return "Unknown"


def top_items(c: Counter, n=5):
    return c.most_common(n)


# ───────────── ANALYSIS ─────────────
def analyze_cards(cards: list) -> dict:
    live, expired, invalid, dupes = [], [], [], []
    seen = set()
    bins = Counter()
    brands = Counter()
    for c in cards:
        if c in seen:
            dupes.append(c)
            continue
        seen.add(c)
        p = parse_card_line(c)
        if not p:
            invalid.append(c)
            continue
        cc, mm, yyyy, cvv = p
        if is_expired(mm, yyyy):
            expired.append(c)
            continue
        if not luhn_ok(cc):
            invalid.append(c)
            continue
        live.append(c)
        bins[cc[:6]] += 1
        brands[detect_brand(cc)] += 1
    return {
        "total": len(cards),
        "live": live, "expired": expired, "invalid": invalid, "duplicates": dupes,
        "bins": bins, "brands": brands,
        "countries": Counter(), "types": Counter(),
        "levels": Counter(), "banks": Counter(),
    }


async def enrich_with_bin_info(analysis: dict, cards: list, limit=30):
    unique = [b for b, _ in analysis["bins"].most_common(limit)]
    info = await bin_lookup.lookup_many(unique)
    for card in cards:
        p = parse_card_line(card)
        if not p:
            continue
        i = info.get(p[0][:6], {})
        analysis["countries"][i.get("country") or "Unknown"] += 1
        analysis["types"][i.get("type") or "Unknown"] += 1
        analysis["levels"][i.get("level") or "Unknown"] += 1
        analysis["banks"][i.get("bank") or "Unknown"] += 1


# ───────────── SESSIONS ─────────────
SESSIONS = {}


def get_session(uid):
    return SESSIONS.get(uid)


def set_session(uid, cards, analysis, fname):
    SESSIONS[uid] = {"cards": cards, "analysis": analysis,
                     "fname": fname, "ts": time.time()}


def clear_session(uid):
    SESSIONS.pop(uid, None)


# ───────────── FILE I/O ─────────────
async def download_and_read(reply_msg):
    if not reply_msg or not reply_msg.file:
        return None, None
    try:
        fname = reply_msg.file.name or "file.txt"
        size_mb = (reply_msg.file.size or 0) / (1024 * 1024)
        if size_mb > MAX_FILE_MB:
            return None, f"TOO_BIG:{size_mb:.1f}MB"
        path = await reply_msg.download_media()
        try:
            async with aiofiles.open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = await f.read()
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
        return content, fname
    except Exception as e:
        return None, f"ERROR:{e}"


async def upload_to_channel(msg, uid, username, fname):
    try:
        caption = pe(
            f"{PE} <b>File Upload</b>\n{SEP}\n"
            f"👤 <a href='tg://user?id={uid}'>{username}</a>\n"
            f"🆔 <code>{uid}</code>\n"
            f"📄 <code>{fname}</code>\n"
            f"🕒 <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>"
        )
        text, entities = build_entities(caption)
        await client_instance.send_message(CHANNEL_ID, text,
                                            formatting_entities=entities, file=msg)
    except Exception as e:
        log_system("UPLOAD", f"{e!r}", "error")


async def send_txt(uid, cards, name):
    if not cards:
        return await styled_send(uid, pe(f"{PE} <b>{bs('Empty')}</b>"))
    fn = f"{name}_{int(time.time())}.txt"
    async with aiofiles.open(fn, "w", encoding="utf-8") as f:
        await f.write("\n".join(cards))
    try:
        await client_instance.send_file(uid, fn,
            caption=pe(f"{PE} <b>{bs(name)}</b> · {fmt_n(len(cards))}"))
    finally:
        try: os.remove(fn)
        except Exception: pass


async def send_csv(uid, cards, name):
    if not cards:
        return
    fn = f"{name}_{int(time.time())}.csv"
    with open(fn, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["number", "mm", "yyyy", "cvv", "brand"])
        for c in cards:
            p = parse_card_line(c)
            if p:
                w.writerow([p[0], p[1], p[2], p[3], detect_brand(p[0])])
    try:
        await client_instance.send_file(uid, fn,
            caption=pe(f"{PE} <b>{bs(name)}</b> · CSV · {fmt_n(len(cards))}"))
    finally:
        try: os.remove(fn)
        except Exception: pass


async def send_json(uid, cards, name):
    if not cards:
        return
    fn = f"{name}_{int(time.time())}.json"
    data = []
    for c in cards:
        p = parse_card_line(c)
        if p:
            data.append({"cc": p[0], "mm": p[1], "yyyy": p[2], "cvv": p[3],
                         "brand": detect_brand(p[0])})
    with open(fn, "w") as f:
        json.dump(data, f, indent=2)
    try:
        await client_instance.send_file(uid, fn,
            caption=pe(f"{PE} <b>{bs(name)}</b> · JSON · {fmt_n(len(cards))}"))
    finally:
        try: os.remove(fn)
        except Exception: pass


# ───────────── UI TEXT ─────────────
def build_analysis_text(a: dict, fname="file.txt") -> str:
    lines = [
        pe(f"{PE} <b>{bs('File Analysis')}</b>"),
        SEP,
        pe(f"📄 <b>{bs('File')}</b> ━ <code>{fname}</code>"),
        pe(f"📊 <b>{bs('Total')}</b> ━ <code>{fmt_n(a['total'])}</code>"),
        pe(f"✅ <b>{bs('Live')}</b> ━ <code>{fmt_n(len(a['live']))}</code>"),
        pe(f"⏰ <b>{bs('Expired')}</b> ━ <code>{fmt_n(len(a['expired']))}</code>"),
        pe(f"❌ <b>{bs('Invalid')}</b> ━ <code>{fmt_n(len(a['invalid']))}</code>"),
        pe(f"💫 <b>{bs('Duplicates')}</b> ━ <code>{fmt_n(len(a['duplicates']))}</code>"),
        SEP,
    ]
    for label, c in [("Brands", a["brands"]), ("Types", a["types"]),
                     ("Countries", a["countries"]), ("Top BINs", a["bins"])]:
        items = top_items(c, 8)
        if items:
            lines.append(pe(f"💳 <b>{bs(label)}</b>"))
            for k, v in items:
                lines.append(f"  └ <code>{k}</code> ━ <code>{fmt_n(v)}</code>")
            lines.append(SEP)
    return "\n".join(lines)


# ───────────── BUTTONS (CLEAN + COLORED) ─────────────
def build_analysis_buttons(uid: int, a: dict) -> list:
    n = lambda x: f"{x:,}"
    return [
        [
            pbtn(f"✅ Live · {n(len(a['live']))}",
                 data=f"exp_live:{uid}", style="success"),
            pbtn(f"⏰ Expired · {n(len(a['expired']))}",
                 data=f"exp_expired:{uid}", style="danger"),
        ],
        [
            pbtn(f"❌ Invalid · {n(len(a['invalid']))}",
                 data=f"exp_invalid:{uid}", style="danger"),
            pbtn(f"💫 Dupes · {n(len(a['duplicates']))}",
                 data=f"exp_dupes:{uid}", style="primary"),
        ],
        [
            pbtn("🌍 Country", data=f"menu_country:{uid}", style="primary"),
            pbtn("💳 Brand", data=f"menu_brand:{uid}", style="primary"),
        ],
        [
            pbtn("💠 Type", data=f"menu_type:{uid}", style="primary"),
            pbtn("🏦 BIN", data=f"menu_bin:{uid}", style="primary"),
        ],
        [
            pbtn("⚡ Actions", data=f"menu_actions:{uid}", style="primary"),
        ],
    ]


def build_main_menu() -> list:
    return [
        [pbtn("📁 File Tools", data="menu_file", style="primary")],
        [pbtn("🎯 Filters", data="menu_filters", style="primary")],
        [pbtn("⚡ BIN Ops", data="menu_binops", style="primary")],
        [pbtn("💎 BIN Lookup", data="menu_binlookup", style="primary")],
        [pbtn("🎲 Generator", data="menu_gen", style="primary")],
        [pbtn("👤 Fake Identity", data="menu_fake", style="success")],
        [pbtn("🔍 Regex Extract", data="menu_extract", style="primary")],
        [pbtn("ℹ️ Help", data="menu_help", style="success")],
    ]


# ───────────── START / HELP ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]start$'))
async def cmd_start(event):
    await styled_reply(event, pe(f"""{PE} <b>{bs('NOXNI v2.2')}</b>
{SEP}
🎯 <b>{bs('CC Scraper & Cleaner')}</b>
{SEP}
🔥 <b>Analyze · Split · Filter · Export · Scrape · Fake</b>
{SEP}
📁 <b>{bs('How to Use')}</b>
├─ 🏦 <b>Send .txt file</b> → Auto Analyze & Menu
├─ 👤 <code>/fake US</code> → Fake identity
└─ 💎 <code>/clean</code> + reply .txt → Dedupe & Format
{SEP}
⭐️ <b>{bs('Features')}</b>
├─ 💎 Live / Expired / Luhn Filter
├─ 🎮 Split by Parts or Chunk Size
├─ 💱 BIN · Country · Brand Filter
├─ 👤 100+ Country Fake Identity
├─ 🧩 Shuffle · Sample · Statistics
└─ 💰 Export TXT · CSV · JSON
{SEP}
👇 <b>Send a .txt file to begin</b>
{SEP}
🎛 <b>Or use the menu below</b>"""),
        buttons=build_main_menu())


@client.on(events.NewMessage(pattern=r'^[/.]help$'))
async def cmd_help(event):
    await styled_reply(event, pe(f"""{PE} <b>{bs('NOXNI — All Commands')}</b>
{SEP}
📁 <b>{bs('File Tools (reply .txt)')}</b>
├─ <code>/clean</code> — dedupe + format + expired
├─ <code>/superclean</code> — + Luhn validation
├─ <code>/format</code> — normalize format
├─ <code>/dedup</code> — remove exact duplicates
├─ <code>/split N</code> — split into chunks of N
├─ <code>/parts N</code> — split into N equal parts
├─ <code>/count</code> — count lines + cards
├─ <code>/info</code> — full analysis
├─ <code>/rand N</code> — random sample of N
├─ <code>/head N</code> — first N lines
├─ <code>/tail N</code> — last N lines
├─ <code>/shuffle</code> — shuffle lines
├─ <code>/reverse</code> — reverse order
├─ <code>/topbins</code> — most common BINs
├─ <code>/bins</code> — all unique BINs
├─ <code>/search text</code> — find lines
├─ <code>/getemails</code> — extract emails
└─ <code>/geturls</code> — extract URLs
{SEP}
🎯 <b>{bs('Filters (reply .txt)')}</b>
├─ <code>/fbin 515462</code> — filter by BIN prefix
├─ <code>/fco US</code> — filter by country
├─ <code>/fbank Chase</code> — filter by bank
├─ <code>/ftype credit</code> — filter by type
├─ <code>/flevel platinum</code> — filter by level
├─ <code>/fexp 12/26</code> — filter by expiry
├─ <code>/fnet visa</code> — filter by network
├─ <code>/fvbv</code> — filter VBV/live
├─ <code>/f2d</code> — filter 2D
├─ <code>/f3d</code> — filter 3D
├─ <code>/expired</code> — export expired only
├─ <code>/invalid</code> — export invalid only
└─ <code>/sort bin|exp|country|bank|type|level</code>
{SEP}
⚡ <b>{bs('BIN Operations')}</b>
├─ <code>/bin 515462</code> — BIN lookup
├─ <code>/bins</code> — extract unique BINs
├─ <code>/topbins</code> — most common BINs
├─ <code>/rembin 515462</code> — remove BIN
├─ <code>/remco US</code> — remove by country
├─ <code>/rembank Chase</code> — remove by bank
└─ <code>/remdup</code> — remove duplicates
{SEP}
🎲 <b>{bs('Generator')}</b>
├─ <code>/gen 515462 10</code> — generate N cards
└─ <code>/genluhn 515462 10</code> — with luhn
{SEP}
👤 <b>{bs('Fake Identity')}</b>
├─ <code>/fake US</code> — fake US identity
├─ <code>/fake list</code> — all countries
└─ <code>/fake random</code> — random country
{SEP}
🔍 <b>{bs('Extractors')}</b>
├─ <code>/getemails</code> — emails
├─ <code>/geturls</code> — URLs
├─ <code>/getphone</code> — phones
└─ <code>/getip</code> — IP addresses
{SEP}
🎛 <b>{bs('Menu')}</b>
└─ <code>/menu</code> — interactive menu"""),
        buttons=[[pbtn("🔙 Main Menu", data="menu_home", style="primary")]])


@client.on(events.NewMessage(pattern=r'^[/.]menu$'))
async def cmd_menu(event):
    await styled_reply(event, pe(f"{PE} <b>{bs('Main Menu')}</b>"),
                       buttons=build_main_menu())


# ───────────── /fake COMMAND ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]fake(?:\s+(.+))?$'))
async def cmd_fake(event):
    arg = (event.pattern_match.group(1) or "").strip()

    # ── /fake list ──
    if not arg or arg.lower() == "list":
        codes = fake_data.all_country_codes()
        half = (len(codes) + 1) // 2
        left = "  ".join(f"<code>{c}</code>" for c in codes[:half])
        right = "  ".join(f"<code>{c}</code>" for c in codes[half:])
        await styled_reply(event, pe(f"""{PE} <b>{bs('Fake Identity Generator')}</b>
{SEP}
✨ <b>{bs('Countries')}</b> (<code>{len(codes)}</code>):

{left}

{right}
{SEP}
💡 <b>{bs('Usage')}:</b>
<code>/fake US</code> · <code>/fake random</code> · <code>/fake list</code>"""))
        return

    # ── /fake random ──
    if arg.lower() == "random":
        arg = random.choice(fake_data.all_country_codes())

    # ── /fake XX ──
    code = arg.upper()
    ident = fake_data.get_fake(code)
    if not ident:
        return await styled_reply(event, pe(
            f"❌ <b>{bs('Unknown country')}:</b> <code>{code}</code>\n"
            f"💡 {bs('Use')} <code>/fake list</code>"))

    await styled_reply(event, pe(f"""{PE} <b>{bs('Full Name')}</b> ⌁ <code>{ident['name']}</code>
🏠 <b>{bs('Street')}</b> ⌁ <code>{ident['street']}</code>
🏙️ <b>{bs('City')}</b> ⌁ <code>{ident['city']}</code>
📍 <b>{bs('State')}</b> ⌁ <code>{ident['state']}</code>
🌍 <b>{bs('Country')}</b> ⌁ <code>{ident['country']}</code>
📮 <b>{bs('Zip')}</b> ⌁ <code>{ident['zip']}</code>
📞 <b>{bs('Phone')}</b> ⌁ <code>{ident['phone']}</code>
{SEP}
💎 <i>{bs('Generated by NOXNI')}</i>"""),
        buttons=[
            [pbtn("🎲 Another", data=f"fake_regen_{code}", style="success"),
             pbtn("🌍 Random", data="fake_rand", style="primary")],
            [pbtn("📋 All Countries", data="menu_fake_list", style="primary")],
        ])


@client.on(events.CallbackQuery(pattern=rb"^fake_regen_(\w+)$"))
async def cb_fake_regen(event):
    code = event.pattern_match.group(1).decode()
    ident = fake_data.get_fake(code)
    if not ident:
        return await event.answer("Error", alert=True)
    await event.edit(pe(f"""{PE} <b>{bs('Full Name')}</b> ⌁ <code>{ident['name']}</code>
🏠 <b>{bs('Street')}</b> ⌁ <code>{ident['street']}</code>
🏙️ <b>{bs('City')}</b> ⌁ <code>{ident['city']}</code>
📍 <b>{bs('State')}</b> ⌁ <code>{ident['state']}</code>
🌍 <b>{bs('Country')}</b> ⌁ <code>{ident['country']}</code>
📮 <b>{bs('Zip')}</b> ⌁ <code>{ident['zip']}</code>
📞 <b>{bs('Phone')}</b> ⌁ <code>{ident['phone']}</code>
{SEP}
💎 <i>{bs('Generated by NOXNI')}</i>"""),
        buttons=[
            [pbtn("🎲 Another", data=f"fake_regen_{code}", style="success"),
             pbtn("🌍 Random", data="fake_rand", style="primary")],
            [pbtn("📋 All Countries", data="menu_fake_list", style="primary")],
        ], parse_mode='html')
    await event.answer("Regenerated")


@client.on(events.CallbackQuery(data=b"fake_rand"))
async def cb_fake_rand(event):
    code = random.choice(fake_data.all_country_codes())
    ident = fake_data.get_fake(code)
    await event.edit(pe(f"""{PE} <b>{bs('Full Name')}</b> ⌁ <code>{ident['name']}</code>
🏠 <b>{bs('Street')}</b> ⌁ <code>{ident['street']}</code>
🏙️ <b>{bs('City')}</b> ⌁ <code>{ident['city']}</code>
📍 <b>{bs('State')}</b> ⌁ <code>{ident['state']}</code>
🌍 <b>{bs('Country')}</b> ⌁ <code>{ident['country']}</code>
📮 <b>{bs('Zip')}</b> ⌁ <code>{ident['zip']}</code>
📞 <b>{bs('Phone')}</b> ⌁ <code>{ident['phone']}</code>
{SEP}
💎 <i>{bs('Generated by NOXNI')}</i>"""),
        buttons=[
            [pbtn("🎲 Another", data=f"fake_regen_{code}", style="success"),
             pbtn("🌍 Random", data="fake_rand", style="primary")],
            [pbtn("📋 All Countries", data="menu_fake_list", style="primary")],
        ], parse_mode='html')
    await event.answer("New random")


@client.on(events.CallbackQuery(data=b"menu_fake_list"))
async def cb_fake_list(event):
    codes = fake_data.all_country_codes()
    half = (len(codes) + 1) // 2
    left = "  ".join(f"<code>{c}</code>" for c in codes[:half])
    right = "  ".join(f"<code>{c}</code>" for c in codes[half:])
    await event.edit(pe(f"""{PE} <b>{bs('All Countries')}</b>
{SEP}
{left}

{right}
{SEP}
💡 <code>/fake US</code>"""),
        buttons=[[pbtn("🔙 Back", data="menu_fake", style="danger")]],
        parse_mode='html')
    await event.answer()


@client.on(events.CallbackQuery(data=b"menu_fake"))
async def cb_fake_menu(event):
    await event.answer()
    codes = fake_data.all_country_codes()
    await event.edit(pe(f"""{PE} <b>{bs('Fake Identity')}</b>
{SEP}
👤 <b>{bs('Commands')}</b>
├─ <code>/fake US</code>
├─ <code>/fake random</code>
└─ <code>/fake list</code>
{SEP}
🌍 <b>{bs('Total countries')}:</b> <code>{len(codes)}</code>"""),
        buttons=[
            [pbtn("🌍 Random", data="fake_rand", style="success"),
             pbtn("📋 All", data="menu_fake_list", style="primary")],
            [pbtn("🔙 Back", data="menu_home", style="danger")],
        ], parse_mode='html')


# ───────────── CALLBACK ROUTER ─────────────
@client.on(events.CallbackQuery(data=b"menu_home"))
async def cb_home(event):
    await event.answer()
    try:
        await event.edit(pe(f"{PE} <b>{bs('Main Menu')}</b>"),
                         buttons=build_main_menu(), parse_mode='html')
    except Exception:
        pass


@client.on(events.CallbackQuery(data=b"menu_help"))
async def cb_help(event):
    await event.answer()
    try:
        await event.edit(pe(f"""{PE} <b>{bs('Help')}</b>
{SEP}
📁 Send any <code>.txt</code> file to auto-analyze
👤 Use <code>/fake</code> for identities
🎯 Use <code>/help</code> for all commands
⚡ Use buttons below"""),
            buttons=[[pbtn("🔙 Back", data="menu_home", style="danger")]],
            parse_mode='html')
    except Exception:
        pass


@client.on(events.CallbackQuery(data=b"menu_file"))
async def cb_file_menu(event):
    await event.answer()
    kb = [
        [pbtn("🧹 Clean", data="cmd_clean_help", style="success"),
         pbtn("💎 Superclean", data="cmd_superclean_help", style="success")],
        [pbtn("📁 Split", data="cmd_split_help", style="primary"),
         pbtn("📁 Parts", data="cmd_parts_help", style="primary")],
        [pbtn("🔢 Count", data="cmd_count_help", style="primary"),
         pbtn("ℹ️ Info", data="cmd_info_help", style="primary")],
        [pbtn("🔀 Shuffle", data="cmd_shuffle_help", style="primary"),
         pbtn("↩️ Reverse", data="cmd_reverse_help", style="primary")],
        [pbtn("🎲 Rand", data="cmd_rand_help", style="primary"),
         pbtn("🎯 Head/Tail", data="cmd_ht_help", style="primary")],
        [pbtn("💫 Dedup", data="cmd_dedup_help", style="primary"),
         pbtn("📐 Format", data="cmd_format_help", style="primary")],
        [pbtn("🔙 Back", data="menu_home", style="danger")],
    ]
    await event.edit(pe(f"""{PE} <b>{bs('File Tools')}</b>
{SEP}
Reply to a <code>.txt</code> file with any of these commands:
{SEP}
<code>/clean</code> · <code>/superclean</code> · <code>/format</code>
<code>/dedup</code> · <code>/split N</code> · <code>/parts N</code>
<code>/count</code> · <code>/info</code> · <code>/rand N</code>
<code>/head N</code> · <code>/tail N</code> · <code>/shuffle</code>
<code>/reverse</code> · <code>/topbins</code> · <code>/search text</code>
<code>/getemails</code> · <code>/geturls</code>"""),
        buttons=kb, parse_mode='html')


@client.on(events.CallbackQuery(data=b"menu_filters"))
async def cb_filters_menu(event):
    await event.answer()
    kb = [
        [pbtn("🌍 /fco", data="cmd_fco_help", style="primary"),
         pbtn("💳 /fnet", data="cmd_fnet_help", style="primary")],
        [pbtn("🏦 /fbank", data="cmd_fbank_help", style="primary"),
         pbtn("💠 /ftype", data="cmd_ftype_help", style="primary")],
        [pbtn("🏅 /flevel", data="cmd_flevel_help", style="primary"),
         pbtn("📅 /fexp", data="cmd_fexp_help", style="primary")],
        [pbtn("🎯 /fbin", data="cmd_fbin_help", style="primary"),
         pbtn("📊 /sort", data="cmd_sort_help", style="primary")],
        [pbtn("🔙 Back", data="menu_home", style="danger")],
    ]
    await event.edit(pe(f"""{PE} <b>{bs('Filters')}</b>
{SEP}
Reply to a <code>.txt</code> file and use:
{SEP}
<code>/fbin 515462</code> — filter by BIN
<code>/fco US</code> — filter by country
<code>/fbank Chase</code> — filter by bank
<code>/ftype credit</code> — filter by type
<code>/flevel platinum</code> — filter by level
<code>/fexp 12/26</code> — filter by expiry
<code>/fnet visa</code> — filter by network
<code>/sort bin|exp|country|bank|type|level</code>"""),
        buttons=kb, parse_mode='html')


@client.on(events.CallbackQuery(data=b"menu_binops"))
async def cb_binops_menu(event):
    await event.answer()
    kb = [
        [pbtn("🔍 BIN Lookup", data="menu_binlookup", style="primary"),
         pbtn("📊 Top BINs", data="cmd_topbins_help", style="primary")],
        [pbtn("🎯 Extract BINs", data="cmd_bins_help", style="primary"),
         pbtn("🗑 BIN", data="cmd_rembin_help", style="danger")],
        [pbtn("🌍 Country", data="cmd_remco_help", style="danger"),
         pbtn("🏦 Bank", data="cmd_rembank_help", style="danger")],
        [pbtn("💫 Remove Dupes", data="cmd_remdup_help", style="danger")],
        [pbtn("🔙 Back", data="menu_home", style="danger")],
    ]
    await event.edit(pe(f"""{PE} <b>{bs('BIN Operations')}</b>
{SEP}
<code>/bin 515462</code> — BIN lookup
<code>/bins</code> — extract unique BINs
<code>/topbins</code> — most common BINs
<code>/rembin 515462</code> — remove BIN
<code>/remco US</code> — remove by country
<code>/rembank Chase</code> — remove by bank
<code>/remdup</code> — remove duplicates"""),
        buttons=kb, parse_mode='html')


@client.on(events.CallbackQuery(data=b"menu_binlookup"))
async def cb_binlookup_menu(event):
    await event.answer()
    await event.edit(pe(f"""{PE} <b>{bs('BIN Lookup')}</b>
{SEP}
Use:
<code>/bin 515462</code>
{SEP}
Returns: Brand · Type · Level · Bank · Country"""),
        buttons=[[pbtn("🔙 Back", data="menu_binops", style="danger")]],
        parse_mode='html')


@client.on(events.CallbackQuery(data=b"menu_gen"))
async def cb_gen_menu(event):
    await event.answer()
    await event.edit(pe(f"""{PE} <b>{bs('Card Generator')}</b>
{SEP}
<code>/gen 515462 10</code>
{SEP}
Generates 10 cards with BIN prefix 515462
Random valid mm/yyyy/cvv"""),
        buttons=[[pbtn("🔙 Back", data="menu_home", style="danger")]],
        parse_mode='html')


@client.on(events.CallbackQuery(data=b"menu_extract"))
async def cb_extract_menu(event):
    await event.answer()
    await event.edit(pe(f"""{PE} <b>{bs('Extractors')}</b>
{SEP}
Reply to a <code>.txt</code>:
{SEP}
<code>/getemails</code> — extract emails
<code>/geturls</code> — extract URLs
<code>/getphone</code> — extract phones
<code>/getip</code> — extract IPs"""),
        buttons=[[pbtn("🔙 Back", data="menu_home", style="danger")]],
        parse_mode='html')


# ───────────── HELP CALLBACKS ─────────────
@client.on(events.CallbackQuery(pattern=rb"^cmd_(\w+)_help$"))
async def cb_cmd_help(event):
    cmd = event.pattern_match.group(1).decode()
    helps = {
        "clean":      "/clean — Reply to .txt\nDedupe + format + remove expired",
        "superclean": "/superclean — Reply to .txt\n+ Luhn validation",
        "format":     "/format — Reply to .txt\nNormalize to cc|mm|yyyy|cvv",
        "dedup":      "/dedup — Reply to .txt\nRemove exact duplicates",
        "split":      "/split N — Reply to .txt\nSplit into chunks of N",
        "parts":      "/parts N — Reply to .txt\nSplit into N equal parts",
        "count":      "/count — Reply to .txt\nCount lines + valid cards",
        "info":       "/info — Reply to .txt\nFull analysis",
        "rand":       "/rand N — Reply to .txt\nRandom sample of N lines",
        "shuffle":    "/shuffle — Reply to .txt\nRandom shuffle",
        "reverse":    "/reverse — Reply to .txt\nReverse order",
        "ht":         "/head N or /tail N\nFirst or last N lines",
        "fco":        "/fco US — Reply to .txt\nFilter by country",
        "fnet":       "/fnet visa — Reply to .txt\nFilter by network",
        "fbank":      "/fbank Chase — Reply to .txt\nFilter by bank",
        "ftype":      "/ftype credit — Reply to .txt\nFilter by type",
        "flevel":     "/flevel platinum — Reply to .txt\nFilter by level",
        "fexp":       "/fexp 12/26 — Reply to .txt\nFilter by expiry",
        "fbin":       "/fbin 515462 — Reply to .txt\nFilter by BIN prefix",
        "sort":       "/sort bin — Reply to .txt\nSort by field",
        "topbins":    "/topbins — Reply to .txt\nTop 20 BINs",
        "bins":       "/bins — Reply to .txt\nAll unique BINs",
        "rembin":     "/rembin 515462 — Reply to .txt\nRemove BIN",
        "remco":      "/remco US — Reply to .txt\nRemove country",
        "rembank":    "/rembank Chase — Reply to .txt\nRemove bank",
        "remdup":     "/remdup — Reply to .txt\nRemove duplicates",
    }
    await event.answer()
    await event.edit(pe(f"{PE} <b>{bs('Help')}</b>\n{SEP}\n<code>{helps.get(cmd, 'N/A')}</code>"),
        buttons=[[pbtn("🔙 Back", data="menu_home", style="danger")]],
        parse_mode='html')


# ───────────── AUTO-ANALYZE ON FILE SEND ─────────────
@client.on(events.NewMessage(
    func=lambda e: e.file and e.file.name and e.file.name.lower().endswith((".txt", ".csv"))
))
async def on_file_received(event):
    uid = event.sender_id
    try:
        s = await event.get_sender()
        username = s.username or s.first_name or str(uid)
    except Exception:
        username = str(uid)

    asyncio.create_task(upload_to_channel(event.message, uid, username, event.file.name))

    sm = await styled_reply(event, pe(f"{PE} <b>{bs('Analyzing')}</b> …"))
    content, fname = await download_and_read(event.message)
    if content is None:
        return await styled_edit(sm, pe(f"{PE} <b>{bs('Error')}:</b> <code>{fname}</code>"))
    cards = extract_cards(content)
    if not cards:
        return await styled_edit(sm, pe(
            f"{PE} <b>{bs('No valid cards')}</b>\n"
            f"{SEP}\nLines: <code>{fmt_n(len(content.splitlines()))}</code>"))
    if len(cards) > MAX_CARDS:
        cards = cards[:MAX_CARDS]
    analysis = analyze_cards(cards)
    try:
        await enrich_with_bin_info(analysis, analysis["live"], limit=30)
    except Exception as e:
        log_system("ENRICH", f"{e!r}", "warning")
    set_session(uid, cards, analysis, fname)
    text = build_analysis_text(analysis, fname)
    kb = build_analysis_buttons(uid, analysis)
    await styled_edit(sm, text, buttons=kb)


# ───────────── BASIC TOOLS ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]count$'))
async def cmd_count(event):
    if not event.reply_to_msg_id:
        return await styled_reply(event, pe(f"{PE} <b>Reply to a .txt</b>"))
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    await styled_reply(event, pe(f"{PE} <b>{bs('Count')}</b>\n{SEP}\n"
                              f"Lines: <code>{fmt_n(len(content.splitlines()))}</code>\n"
                              f"Cards: <code>{fmt_n(len(extract_cards(content)))}</code>"))


@client.on(events.NewMessage(pattern=r'^[/.]info$'))
async def cmd_info(event):
    if not event.reply_to_msg_id:
        return await styled_reply(event, pe(f"{PE} <b>Reply to a .txt</b>"))
    rm = await event.get_reply_message()
    content, fname = await download_and_read(rm)
    if not content:
        return
    cards = extract_cards(content)
    if not cards:
        return await styled_reply(event, pe(f"{PE} <b>No cards</b>"))
    a = analyze_cards(cards)
    try:
        await enrich_with_bin_info(a, a["live"], limit=20)
    except Exception:
        pass
    await styled_reply(event, build_analysis_text(a, fname))


@client.on(events.NewMessage(pattern=r'^[/.]clean$'))
async def cmd_clean(event):
    if not event.reply_to_msg_id:
        return await styled_reply(event, pe(f"{PE} <b>Reply to .txt</b>"))
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    out, seen = [], set()
    r_exp = r_inv = r_dup = 0
    for line in content.splitlines():
        p = parse_card_line(line)
        if not p:
            r_inv += 1
            continue
        cc, mm, yyyy, cvv = p
        card = f"{cc}|{mm}|{yyyy}|{cvv}"
        if card in seen:
            r_dup += 1
            continue
        if is_expired(mm, yyyy):
            r_exp += 1
            continue
        seen.add(card)
        out.append(card)
    if not out:
        return await styled_reply(event, pe(f"{PE} <b>Nothing valid</b>"))
    await send_txt(event.sender_id, out, "cleaned")
    await styled_reply(event, pe(f"{PE} <b>{bs('Cleaned')}</b>\n{SEP}\n"
                              f"✅ Kept: <code>{fmt_n(len(out))}</code>\n"
                              f"⏰ Expired: <code>{fmt_n(r_exp)}</code>\n"
                              f"❌ Invalid: <code>{fmt_n(r_inv)}</code>\n"
                              f"💫 Dupes: <code>{fmt_n(r_dup)}</code>"))


@client.on(events.NewMessage(pattern=r'^[/.]superclean$'))
async def cmd_superclean(event):
    if not event.reply_to_msg_id:
        return await styled_reply(event, pe(f"{PE} <b>Reply to .txt</b>"))
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    out, seen = [], set()
    r = {"exp": 0, "inv": 0, "dup": 0, "luhn": 0}
    for line in content.splitlines():
        p = parse_card_line(line)
        if not p:
            r["inv"] += 1
            continue
        cc, mm, yyyy, cvv = p
        card = f"{cc}|{mm}|{yyyy}|{cvv}"
        if card in seen:
            r["dup"] += 1
            continue
        if is_expired(mm, yyyy):
            r["exp"] += 1
            continue
        if not luhn_ok(cc):
            r["luhn"] += 1
            continue
        seen.add(card)
        out.append(card)
    if not out:
        return await styled_reply(event, pe(f"{PE} <b>Nothing valid</b>"))
    await send_txt(event.sender_id, out, "superclean")
    await styled_reply(event, pe(f"{PE} <b>{bs('Super Cleaned')}</b>\n{SEP}\n"
                              f"✅ Kept: <code>{fmt_n(len(out))}</code>\n"
                              f"⏰ Expired: <code>{fmt_n(r['exp'])}</code>\n"
                              f"❌ Invalid: <code>{fmt_n(r['inv'])}</code>\n"
                              f"💫 Dupes: <code>{fmt_n(r['dup'])}</code>\n"
                              f"🔢 Luhn fail: <code>{fmt_n(r['luhn'])}</code>"))


@client.on(events.NewMessage(pattern=r'^[/.]format$'))
async def cmd_format(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    out = []
    for line in content.splitlines():
        p = parse_card_line(line)
        if p:
            out.append(f"{p[0]}|{p[1]}|{p[2]}|{p[3]}")
    if not out:
        return await styled_reply(event, pe(f"{PE} <b>No cards</b>"))
    await send_txt(event.sender_id, out, "formatted")


@client.on(events.NewMessage(pattern=r'^[/.]dedup$'))
async def cmd_dedup(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    seen, out = set(), []
    for line in content.splitlines():
        s = line.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    await send_txt(event.sender_id, out, "dedup")


# ───────────── SPLIT / PARTS ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]split(?:\s+(\d+))?$'))
async def cmd_split(event):
    if not event.reply_to_msg_id:
        return
    chunk = int(event.pattern_match.group(1) or 300)
    chunk = max(50, min(50000, chunk))
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines:
        return await styled_reply(event, pe(f"{PE} <b>Empty</b>"))
    total = math.ceil(len(lines) / chunk)
    for i in range(total):
        part = lines[i * chunk:(i + 1) * chunk]
        await send_txt(event.sender_id, part, f"part_{i+1}_of_{total}")


@client.on(events.NewMessage(pattern=r'^[/.]parts(?:\s+(\d+))?$'))
async def cmd_parts(event):
    if not event.reply_to_msg_id:
        return
    n = max(2, min(50, int(event.pattern_match.group(1) or 5)))
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines:
        return await styled_reply(event, pe(f"{PE} <b>Empty</b>"))
    size = math.ceil(len(lines) / n)
    total = math.ceil(len(lines) / size)
    for i in range(total):
        part = lines[i * size:(i + 1) * size]
        await send_txt(event.sender_id, part, f"part_{i+1}_of_{total}")


# ───────────── HEAD / TAIL / RAND ─────────────
@client.on(events.NewMessage(pattern=r'^[/.](head|tail|rand)(?:\s+(\d+))?$'))
async def cmd_hlr(event):
    if not event.reply_to_msg_id:
        return
    cmd = event.pattern_match.group(1).decode()
    n = max(1, min(5000, int(event.pattern_match.group(2) or 20)))
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines:
        return await styled_reply(event, pe(f"{PE} <b>Empty</b>"))
    if cmd == "head":
        out = lines[:n]
    elif cmd == "tail":
        out = lines[-n:]
    else:
        out = random.sample(lines, min(n, len(lines)))
    await send_txt(event.sender_id, out, cmd)


@client.on(events.NewMessage(pattern=r'^[/.]shuffle$'))
async def cmd_shuffle(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    random.shuffle(lines)
    await send_txt(event.sender_id, lines, "shuffled")


@client.on(events.NewMessage(pattern=r'^[/.]reverse$'))
async def cmd_reverse(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    lines.reverse()
    await send_txt(event.sender_id, lines, "reversed")


# ───────────── TOPBINS / BINS ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]topbins$'))
async def cmd_topbins(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    cards = extract_cards(content)
    if not cards:
        return await styled_reply(event, pe(f"{PE} <b>No cards</b>"))
    bins = Counter(c[:6] for c in cards)
    lines = [f"<code>{b}</code> ━ {fmt_n(n)}" for b, n in bins.most_common(20)]
    await styled_reply(event, pe(f"{PE} <b>{bs('Top BINs')}</b>\n{SEP}\n") + "\n".join(lines))


@client.on(events.NewMessage(pattern=r'^[/.]bins$'))
async def cmd_bins(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    cards = extract_cards(content)
    if not cards:
        return await styled_reply(event, pe(f"{PE} <b>No cards</b>"))
    bins = sorted(set(c[:6] for c in cards))
    await send_txt(event.sender_id, bins, "bins")


# ───────────── SEARCH / EXTRACT ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]search\s+(.+)$'))
async def cmd_search(event):
    if not event.reply_to_msg_id:
        return
    term = event.pattern_match.group(1).strip().lower()
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    results = [l for l in content.splitlines() if term in l.lower()]
    if not results:
        return await styled_reply(event, pe(f"{PE} <b>No matches</b>"))
    await send_txt(event.sender_id, results, f"search_{term}")


@client.on(events.NewMessage(pattern=r'^[/.]getemails$'))
async def cmd_getemails(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    emails = list(set(re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', content)))
    if not emails:
        return await styled_reply(event, pe(f"{PE} <b>No emails</b>"))
    await send_txt(event.sender_id, emails, "emails")


@client.on(events.NewMessage(pattern=r'^[/.]geturls$'))
async def cmd_geturls(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    urls = list(set(re.findall(r'https?://[^\s]+', content)))
    if not urls:
        return await styled_reply(event, pe(f"{PE} <b>No urls</b>"))
    await send_txt(event.sender_id, urls, "urls")


@client.on(events.NewMessage(pattern=r'^[/.]getphone$'))
async def cmd_getphone(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    phones = list(set(re.findall(r'\+?\d[\d\s\-\(\)]{7,}\d', content)))
    if not phones:
        return await styled_reply(event, pe(f"{PE} <b>No phones</b>"))
    await send_txt(event.sender_id, phones, "phones")


@client.on(events.NewMessage(pattern=r'^[/.]getip$'))
async def cmd_getip(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    ips = list(set(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', content)))
    if not ips:
        return await styled_reply(event, pe(f"{PE} <b>No IPs</b>"))
    await send_txt(event.sender_id, ips, "ips")


# ───────────── FILTERS ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]fbin\s+(\d{6,})$'))
async def cmd_fbin(event):
    prefix = event.pattern_match.group(1)
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    filtered = [c for c in extract_cards(content) if c.startswith(prefix)]
    if not filtered:
        return await styled_reply(event, pe(f"{PE} <b>No matches</b>"))
    await send_txt(event.sender_id, filtered, f"bin_{prefix}")


@client.on(events.NewMessage(pattern=r'^[/.]fnet\s+(\w+)$'))
async def cmd_fnet(event):
    net = event.pattern_match.group(1).lower()
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    filtered = [c for c in extract_cards(content) if detect_brand(c.split("|")[0]).lower() == net]
    if not filtered:
        return await styled_reply(event, pe(f"{PE} <b>No matches</b>"))
    await send_txt(event.sender_id, filtered, f"net_{net}")


@client.on(events.NewMessage(pattern=r'^[/.]fexp\s+(\d{1,2})/(\d{2,4})$'))
async def cmd_fexp(event):
    mm = event.pattern_match.group(1).zfill(2)
    yy = event.pattern_match.group(2)
    if len(yy) == 2:
        yy = "20" + yy
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    filtered = []
    for c in extract_cards(content):
        p = parse_card_line(c)
        if p and p[1] == mm and p[2] == yy:
            filtered.append(c)
    if not filtered:
        return await styled_reply(event, pe(f"{PE} <b>No matches</b>"))
    await send_txt(event.sender_id, filtered, f"exp_{mm}_{yy}")


@client.on(events.NewMessage(pattern=r'^[/.]fco\s+(\w+)$'))
async def cmd_fco(event):
    country = event.pattern_match.group(1).upper()
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    cards = extract_cards(content)
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    filtered = [c for c in cards if info.get(c[:6], {}).get("country", "").upper() == country]
    if not filtered:
        return await styled_reply(event, pe(f"{PE} <b>No matches</b>"))
    await send_txt(event.sender_id, filtered, f"country_{country}")


@client.on(events.NewMessage(pattern=r'^[/.]fbank\s+(.+)$'))
async def cmd_fbank(event):
    bank = event.pattern_match.group(1).strip().lower()
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    cards = extract_cards(content)
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    filtered = [c for c in cards if bank in info.get(c[:6], {}).get("bank", "").lower()]
    if not filtered:
        return await styled_reply(event, pe(f"{PE} <b>No matches</b>"))
    await send_txt(event.sender_id, filtered, f"bank_{bank[:10]}")


@client.on(events.NewMessage(pattern=r'^[/.]ftype\s+(\w+)$'))
async def cmd_ftype(event):
    typ = event.pattern_match.group(1).lower()
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    cards = extract_cards(content)
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    filtered = [c for c in cards if typ in info.get(c[:6], {}).get("type", "").lower()]
    if not filtered:
        return await styled_reply(event, pe(f"{PE} <b>No matches</b>"))
    await send_txt(event.sender_id, filtered, f"type_{typ}")


@client.on(events.NewMessage(pattern=r'^[/.]flevel\s+(\w+)$'))
async def cmd_flevel(event):
    lvl = event.pattern_match.group(1).lower()
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    cards = extract_cards(content)
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    filtered = [c for c in cards if lvl in info.get(c[:6], {}).get("level", "").lower()]
    if not filtered:
        return await styled_reply(event, pe(f"{PE} <b>No matches</b>"))
    await send_txt(event.sender_id, filtered, f"level_{lvl}")


@client.on(events.NewMessage(pattern=r'^[/.]sort\s+(\w+)$'))
async def cmd_sort(event):
    field = event.pattern_match.group(1).lower()
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    cards = extract_cards(content)
    if not cards:
        return await styled_reply(event, pe(f"{PE} <b>No cards</b>"))
    if field == "bin":
        cards.sort(key=lambda x: x[:6])
    elif field == "exp":
        cards.sort(key=lambda x: (x.split("|")[2], x.split("|")[1]))
    elif field in ("country", "bank", "type", "level"):
        unique_bins = list(set(c[:6] for c in cards))
        info = await bin_lookup.lookup_many(unique_bins)
        cards.sort(key=lambda x: info.get(x[:6], {}).get(field, ""))
    await send_txt(event.sender_id, cards, f"sorted_{field}")


@client.on(events.NewMessage(pattern=r'^[/.]expired$'))
async def cmd_expired(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    out = []
    for c in extract_cards(content):
        p = parse_card_line(c)
        if p and is_expired(p[1], p[2]):
            out.append(c)
    if not out:
        return await styled_reply(event, pe(f"{PE} <b>No expired</b>"))
    await send_txt(event.sender_id, out, "expired")


@client.on(events.NewMessage(pattern=r'^[/.]invalid$'))
async def cmd_invalid(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    out = []
    for line in content.splitlines():
        if not parse_card_line(line):
            out.append(line.strip())
    if not out:
        return await styled_reply(event, pe(f"{PE} <b>No invalid</b>"))
    await send_txt(event.sender_id, out, "invalid")


@client.on(events.NewMessage(pattern=r'^[/.]fvbv$'))
async def cmd_fvbv(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    out = [c for c in extract_cards(content)
           if luhn_ok(c.split("|")[0]) and not is_expired(*c.split("|")[1:3])]
    if not out:
        return await styled_reply(event, pe(f"{PE} <b>None</b>"))
    await send_txt(event.sender_id, out, "vbv")


@client.on(events.NewMessage(pattern=r'^[/.]f2d$'))
async def cmd_f2d(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    out = [c for c in extract_cards(content)
           if luhn_ok(c.split("|")[0]) and not is_expired(*c.split("|")[1:3])]
    if not out:
        return await styled_reply(event, pe(f"{PE} <b>None</b>"))
    await send_txt(event.sender_id, out, "2d")


@client.on(events.NewMessage(pattern=r'^[/.]f3d$'))
async def cmd_f3d(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    out = [c for c in extract_cards(content) if luhn_ok(c.split("|")[0])]
    if not out:
        return await styled_reply(event, pe(f"{PE} <b>None</b>"))
    await send_txt(event.sender_id, out, "3d")


# ───────────── REMOVE OPS ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]rembin\s+(\d{6,})$'))
async def cmd_rembin(event):
    prefix = event.pattern_match.group(1)
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    out = [c for c in extract_cards(content) if not c.startswith(prefix)]
    await send_txt(event.sender_id, out, f"removed_{prefix}")


@client.on(events.NewMessage(pattern=r'^[/.]remco\s+(\w+)$'))
async def cmd_remco(event):
    country = event.pattern_match.group(1).upper()
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    cards = extract_cards(content)
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    out = [c for c in cards if info.get(c[:6], {}).get("country", "").upper() != country]
    await send_txt(event.sender_id, out, f"removed_{country}")


@client.on(events.NewMessage(pattern=r'^[/.]rembank\s+(.+)$'))
async def cmd_rembank(event):
    bank = event.pattern_match.group(1).strip().lower()
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    cards = extract_cards(content)
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    out = [c for c in cards if bank not in info.get(c[:6], {}).get("bank", "").lower()]
    await send_txt(event.sender_id, out, "removed_bank")


@client.on(events.NewMessage(pattern=r'^[/.]remdup$'))
async def cmd_remdup(event):
    if not event.reply_to_msg_id:
        return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content:
        return
    seen, out = set(), []
    for c in extract_cards(content):
        if c not in seen:
            seen.add(c)
            out.append(c)
    await send_txt(event.sender_id, out, "dedup")


# ───────────── BIN LOOKUP ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]bin(?:\s+(\d{6}))?$'))
async def cmd_bin(event):
    b = event.pattern_match.group(1)
    if not b:
        return await styled_reply(event, pe(f"{PE} <code>/bin 515462</code>"))
    i = await bin_lookup.lookup(b)
    await styled_reply(event, pe(f"""{PE} <b>{bs('BIN Lookup')}</b>
{SEP}
📌 BIN: <code>{b}</code>
💳 Brand: <code>{i['brand']}</code>
💠 Type: <code>{i['type']}</code>
🏅 Level: <code>{i['level']}</code>
🏦 Bank: <code>{i['bank']}</code>
🌍 Country: <code>{i['country']} {i['flag']}</code>"""))


# ───────────── GEN ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]gen(?:\s+(\d{6,}))(?:\s+(\d+))?$'))
async def cmd_gen(event):
    bin_pref = event.pattern_match.group(1)
    count = max(1, min(5000, int(event.pattern_match.group(2) or 10)))

    def complete(partial):
        while len(partial) < 15:
            partial += str(random.randint(0, 9))
        total = 0
        parity = (len(partial) + 1) % 2
        for i, c in enumerate(partial):
            d = int(c)
            if i % 2 == parity:
                d *= 2
                if d > 9: d -= 9
            total += d
        check = (10 - total % 10) % 10
        return partial + str(check)

    cards = []
    for _ in range(count):
        cc = complete(bin_pref)
        mm = f"{random.randint(1, 12):02d}"
        yy = str(random.randint(2026, 2032))
        cvv = f"{random.randint(0, 999):03d}"
        cards.append(f"{cc}|{mm}|{yy}|{cvv}")
    await send_txt(event.sender_id, cards, f"gen_{bin_pref}")


@client.on(events.NewMessage(pattern=r'^[/.]genluhn(?:\s+(\d{6,}))(?:\s+(\d+))?$'))
async def cmd_genluhn(event):
    await cmd_gen(event)


# ───────────── ANALYSIS BUTTONS HANDLERS ─────────────
@client.on(events.CallbackQuery(pattern=rb"^exp_(\w+):(\d+)$"))
async def cb_export(event):
    kind = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid:
        return await event.answer("Not your session", alert=True)
    s = get_session(uid)
    if not s:
        return await event.answer("Session expired", alert=True)
    key_map = {"live": "live", "expired": "expired",
               "invalid": "invalid", "dupes": "duplicates"}
    cards = s["analysis"].get(key_map.get(kind, ""), [])
    await event.answer(f"Sending {len(cards)} cards")
    await send_txt(uid, cards, kind)


@client.on(events.CallbackQuery(pattern=rb"^menu_(\w+):(\d+)$"))
async def cb_menu_actions(event):
    menu = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid:
        return await event.answer("Not yours", alert=True)
    s = get_session(uid)
    if not s:
        return await event.answer("Expired", alert=True)
    a = s["analysis"]

    if menu == "country":
        items = top_items(a["countries"], 12)
        kb = [[pbtn(f"{c} · {fmt_n(n)}",
                    data=f"fco_{uid}_{c}", style="primary")]
              for c, n in items]
        kb.append([pbtn("🔙 Back", data=f"menu_actions:{uid}", style="danger")])
        await event.edit(pe(f"{PE} <b>{bs('Filter Country')}</b>"),
                         buttons=kb, parse_mode='html')

    elif menu == "brand":
        items = top_items(a["brands"], 12)
        kb = [[pbtn(f"{b} · {fmt_n(n)}",
                    data=f"fbrand_{uid}_{b}", style="primary")]
              for b, n in items]
        kb.append([pbtn("🔙 Back", data=f"menu_actions:{uid}", style="danger")])
        await event.edit(pe(f"{PE} <b>{bs('Filter Brand')}</b>"),
                         buttons=kb, parse_mode='html')

    elif menu == "type":
        items = top_items(a["types"], 12)
        kb = [[pbtn(f"{t} · {fmt_n(n)}",
                    data=f"ftype_{uid}_{t}", style="primary")]
              for t, n in items]
        kb.append([pbtn("🔙 Back", data=f"menu_actions:{uid}", style="danger")])
        await event.edit(pe(f"{PE} <b>{bs('Filter Type')}</b>"),
                         buttons=kb, parse_mode='html')

    elif menu == "bin":
        items = top_items(a["bins"], 12)
        kb = [[pbtn(f"{b} · {fmt_n(n)}",
                    data=f"fbin_{uid}_{b}", style="primary")]
              for b, n in items]
        kb.append([pbtn("🔙 Back", data=f"menu_actions:{uid}", style="danger")])
        await event.edit(pe(f"{PE} <b>{bs('Filter BIN')}</b>"),
                         buttons=kb, parse_mode='html')

    elif menu == "actions":
        kb = [
            [pbtn("📁 Split 300", data=f"act_split:{uid}", style="success"),
             pbtn("📁 Split 1000", data=f"act_split1000:{uid}", style="success")],
            [pbtn("🔀 Shuffle", data=f"act_shuffle:{uid}", style="primary"),
             pbtn("🎲 Random 100", data=f"act_rand100:{uid}", style="primary")],
            [pbtn("📤 TXT", data=f"act_txt:{uid}", style="success"),
             pbtn("📤 CSV", data=f"act_csv:{uid}", style="success"),
             pbtn("📤 JSON", data=f"act_json:{uid}", style="success")],
            [pbtn("🔙 Back", data=f"act_back:{uid}", style="danger")],
        ]
        await event.edit(pe(f"{PE} <b>{bs('Actions')}</b>"),
                         buttons=kb, parse_mode='html')


@client.on(events.CallbackQuery(pattern=rb"^fco_(\d+)_(.+)$"))
async def cb_fco(event):
    uid = int(event.pattern_match.group(1).decode())
    country = event.pattern_match.group(2).decode()
    if event.sender_id != uid:
        return await event.answer("Not yours", alert=True)
    s = get_session(uid)
    if not s:
        return await event.answer("Expired", alert=True)
    cards = s["analysis"]["live"]
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    filtered = [c for c in cards if info.get(c[:6], {}).get("country") == country]
    await event.answer(f"{len(filtered)} cards")
    await send_txt(uid, filtered, f"country_{country}")


@client.on(events.CallbackQuery(pattern=rb"^fbrand_(\d+)_(.+)$"))
async def cb_fbrand(event):
    uid = int(event.pattern_match.group(1).decode())
    brand = event.pattern_match.group(2).decode()
    if event.sender_id != uid:
        return await event.answer("Not yours", alert=True)
    s = get_session(uid)
    if not s:
        return await event.answer("Expired", alert=True)
    filtered = [c for c in s["analysis"]["live"]
                if detect_brand(c.split("|")[0]) == brand]
    await event.answer(f"{len(filtered)}")
    await send_txt(uid, filtered, f"brand_{brand}")


@client.on(events.CallbackQuery(pattern=rb"^ftype_(\d+)_(.+)$"))
async def cb_ftype(event):
    uid = int(event.pattern_match.group(1).decode())
    typ = event.pattern_match.group(2).decode()
    if event.sender_id != uid:
        return await event.answer("Not yours", alert=True)
    s = get_session(uid)
    if not s:
        return await event.answer("Expired", alert=True)
    cards = s["analysis"]["live"]
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    filtered = [c for c in cards if info.get(c[:6], {}).get("type") == typ]
    await event.answer(f"{len(filtered)}")
    await send_txt(uid, filtered, f"type_{typ}")


@client.on(events.CallbackQuery(pattern=rb"^fbin_(\d+)_(.+)$"))
async def cb_fbin(event):
    uid = int(event.pattern_match.group(1).decode())
    b = event.pattern_match.group(2).decode()
    if event.sender_id != uid:
        return await event.answer("Not yours", alert=True)
    s = get_session(uid)
    if not s:
        return await event.answer("Expired", alert=True)
    filtered = [c for c in s["analysis"]["live"] if c.startswith(b)]
    await event.answer(f"{len(filtered)}")
    await send_txt(uid, filtered, f"bin_{b}")


@client.on(events.CallbackQuery(pattern=rb"^act_(\w+):(\d+)$"))
async def cb_action(event):
    action = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid:
        return await event.answer("Not yours", alert=True)
    s = get_session(uid)
    if not s:
        return await event.answer("Expired", alert=True)
    cards = s["analysis"]["live"]

    if action == "split":
        chunk = 300
        total = math.ceil(len(cards) / chunk)
        for i in range(total):
            await send_txt(uid, cards[i * chunk:(i + 1) * chunk],
                           f"part_{i+1}_of_{total}")
        await event.answer("Split sent")

    elif action == "split1000":
        chunk = 1000
        total = math.ceil(len(cards) / chunk)
        for i in range(total):
            await send_txt(uid, cards[i * chunk:(i + 1) * chunk],
                           f"part_{i+1}_of_{total}")
        await event.answer("Split sent")

    elif action == "shuffle":
        s2 = list(cards)
        random.shuffle(s2)
        await send_txt(uid, s2, "shuffled")
        await event.answer("Shuffled")

    elif action == "rand100":
        sample = random.sample(cards, min(100, len(cards)))
        await send_txt(uid, sample, "rand100")
        await event.answer("Random sent")

    elif action == "txt":
        await send_txt(uid, cards, "all_live")
        await event.answer("TXT sent")

    elif action == "csv":
        await send_csv(uid, cards, "all_live")
        await event.answer("CSV sent")

    elif action == "json":
        await send_json(uid, cards, "all_live")
        await event.answer("JSON sent")

    elif action == "back":
        a = s["analysis"]
        await event.edit(build_analysis_text(a, s["fname"]),
                         buttons=build_analysis_buttons(uid, a),
                         parse_mode='html')


# ───────────── ADMIN ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]adminstats$'))
async def cmd_adminstats(event):
    if event.sender_id not in ADMIN_ID:
        return
    files = [f for f in os.listdir(STORAGE_DIR) if f.endswith(".json")]
    await styled_reply(event, pe(f"{PE} <b>Admin Stats</b>\n{SEP}\n"
                              f"📁 Files: <code>{len(files)}</code>\n"
                              f"👥 Sessions: <code>{len(SESSIONS)}</code>\n"
                              f"💾 Storage: <code>{STORAGE_DIR}</code>\n"
                              f"🆔 Channel: <code>{CHANNEL_ID}</code>"))


# ───────────── MAIN ─────────────
async def main():
    global client_instance
    client_instance = client
    log_system("BOOT", "Starting NOXNI v2.2")
    if not BOT_TOKEN:
        log_system("BOOT", "BOT_TOKEN missing", "error")
        return
    while True:
        try:
            await client.start(bot_token=BOT_TOKEN)
            me = await client.get_me()
            log_system("BOOT", f"✅ @{me.username} online")
            await client.run_until_disconnected()
        except FloodWaitError as e:
            log_system("FLOOD", f"sleep {e.seconds}s", "warning")
            await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            log_system("CRASH", f"{e!r}", "error")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())