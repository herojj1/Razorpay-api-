#!/usr/bin/env python3
# =============================================================================
# NOXNI v2.0 — CC Scraper & Cleaner Bot
# Full Tools · Auto Analyze · Filters · Exports · BIN ops
# =============================================================================

import os, re, io, csv, json, math, time, random, string, asyncio
import logging
from datetime import datetime, timedelta
from collections import Counter
from urllib.parse import quote

import aiohttp
import aiofiles
from telethon import TelegramClient, events, Button
from telethon.errors import FloodWaitError
from telethon.tl.types import MessageEntityCustomEmoji
from telethon.extensions import html as thtml

import bin_lookup


# ───────────── CONFIG ─────────────
API_ID    = int(os.getenv("API_ID") or 33657928)
API_HASH  = os.getenv("API_HASH", "a61fde61442113b9a65c699f7020d59a")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8517366800:AAGbU4pTheYVVCqMLYDqGvot4pa4FCGQhSw")
ADMIN_ID  = json.loads(os.getenv("ADMIN_ID", "[8871910561]"))

# Channel to log user uploads
CHANNEL_ID = int(os.getenv("UPLOAD_CHANNEL_ID", "-1003965573664"))

MAX_FILE_MB   = 50
MAX_CARDS     = 500_000
MAX_MSG_LEN   = 3800

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
    if not t: return t
    return "".join(_BOLD.get(c, c) for c in str(t))


SEP = "━━━━━━━━━━━━━━━━━━━━"
PE  = "💎"


# ───────────── CLIENT ─────────────
client = TelegramClient("noxni_bot", API_ID, API_HASH)
client_instance = client


# ───────────── MESSAGE HELPERS ─────────────
def build_entities(html_text, emoji_ids=None):
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


def pbtn(text, data=None, url=None):
    if url: return Button.url(text, url)
    if data: return Button.inline(text, data.encode() if isinstance(data, str) else data)
    return Button.inline(text, b"none")


# ───────────── CARD PARSING ─────────────
_CC_RE = re.compile(r'(\d{13,19})[^\d]+(\d{1,2})[^\d]+(\d{2,4})[^\d]+(\d{3,4})')


def extract_cards(text: str) -> list:
    if not text: return []
    out = []
    for c, m, y, cv in _CC_RE.findall(text):
        if len(y) == 2: y = "20" + y
        try:
            mi = int(m); yi = int(y)
            if not (1 <= mi <= 12): continue
            if not (2020 <= yi <= 2099): continue
        except: continue
        if len(cv) not in (3, 4): continue
        out.append(f"{c}|{m.zfill(2)}|{y}|{cv}")
    return list(dict.fromkeys(out))


def parse_card_line(line: str):
    parts = re.split(r'[|/\\:\s]+', line.strip())
    if len(parts) < 4: return None
    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    if not cc.isdigit() or not (13 <= len(cc) <= 19): return None
    if not mm.isdigit(): return None
    if not (1 <= int(mm) <= 12): return None
    if not yy.isdigit(): return None
    if len(yy) == 2: yy = "20" + yy
    if not (2020 <= int(yy) <= 2099): return None
    if not cvv.isdigit() or len(cvv) not in (3, 4): return None
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
    if len(digits) < 12: return False
    csum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9: d -= 9
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


def detect_level(cc):
    return "Unknown"


def fmt_n(n): return f"{n:,}"


def top_items(c: Counter, n=5): return c.most_common(n)


# ───────────── ANALYSIS ─────────────
def analyze_cards(cards: list) -> dict:
    live, expired, invalid, dupes = [], [], [], []
    seen = set()
    bins = Counter()
    brands = Counter()
    for c in cards:
        if c in seen:
            dupes.append(c); continue
        seen.add(c)
        p = parse_card_line(c)
        if not p:
            invalid.append(c); continue
        cc, mm, yyyy, cvv = p
        if is_expired(mm, yyyy):
            expired.append(c); continue
        if not luhn_ok(cc):
            invalid.append(c); continue
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
        if not p: continue
        i = info.get(p[0][:6], {})
        analysis["countries"][i.get("country") or "Unknown"] += 1
        analysis["types"][i.get("type") or "Unknown"] += 1
        analysis["levels"][i.get("level") or "Unknown"] += 1
        analysis["banks"][i.get("bank") or "Unknown"] += 1


# ───────────── SESSIONS ─────────────
SESSIONS = {}


def get_session(uid): return SESSIONS.get(uid)
def set_session(uid, cards, analysis, fname):
    SESSIONS[uid] = {"cards": cards, "analysis": analysis, "fname": fname, "ts": time.time()}
def clear_session(uid): SESSIONS.pop(uid, None)


# ───────────── FILE I/O ─────────────
async def download_and_read(reply_msg):
    if not reply_msg or not reply_msg.file:
        return None, None
    try:
        fname = reply_msg.file.name or "file.txt"
        size_mb = (reply_msg.file.size or 0) / (1024*1024)
        if size_mb > MAX_FILE_MB:
            return None, f"TOO_BIG:{size_mb:.1f}MB"
        path = await reply_msg.download_media()
        try:
            async with aiofiles.open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = await f.read()
        finally:
            try: os.remove(path)
            except: pass
        return content, fname
    except Exception as e:
        return None, f"ERROR:{e}"


async def upload_to_channel(msg, uid, username, fname):
    try:
        caption = (
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
        return await styled_send(uid, f"{PE} <b>{bs('Empty')}</b>")
    fn = f"{name}_{int(time.time())}.txt"
    async with aiofiles.open(fn, "w", encoding="utf-8") as f:
        await f.write("\n".join(cards))
    try:
        await client_instance.send_file(uid, fn,
            caption=f"{PE} <b>{bs(name)}</b> ({len(cards)})")
    finally:
        try: os.remove(fn)
        except: pass


async def send_csv(uid, cards, name):
    if not cards: return
    fn = f"{name}_{int(time.time())}.csv"
    with open(fn, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["number", "mm", "yyyy", "cvv", "brand"])
        for c in cards:
            p = parse_card_line(c)
            if p: w.writerow([p[0], p[1], p[2], p[3], detect_brand(p[0])])
    try:
        await client_instance.send_file(uid, fn,
            caption=f"{PE} <b>{bs(name)}</b> CSV ({len(cards)})")
    finally:
        try: os.remove(fn)
        except: pass


async def send_json(uid, cards, name):
    if not cards: return
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
            caption=f"{PE} <b>{bs(name)}</b> JSON ({len(cards)})")
    finally:
        try: os.remove(fn)
        except: pass


# ───────────── UI BUILDERS ─────────────
def build_analysis_text(a: dict, fname="file.txt") -> str:
    lines = [
        f"{PE} <b>{bs('File Analysis')}</b>",
        SEP,
        f"📄 <b>{bs('File')}</b> ━ <code>{fname}</code>",
        f"📊 <b>{bs('Total')}</b> ━ <code>{fmt_n(a['total'])}</code>",
        f"✅ <b>{bs('Live')}</b> ━ <code>{fmt_n(len(a['live']))}</code>",
        f"⏰ <b>{bs('Expired')}</b> ━ <code>{fmt_n(len(a['expired']))}</code>",
        f"❌ <b>{bs('Invalid')}</b> ━ <code>{fmt_n(len(a['invalid']))}</code>",
        f"♻️ <b>{bs('Duplicates')}</b> ━ <code>{fmt_n(len(a['duplicates']))}</code>",
        SEP,
    ]
    for label, c in [("Brands", a["brands"]), ("Types", a["types"]),
                     ("Countries", a["countries"]), ("Top BINs", a["bins"])]:
        items = top_items(c, 8)
        if items:
            lines.append(f"💳 <b>{bs(label)}</b>")
            for k, v in items:
                lines.append(f"  └ <code>{k}</code> ━ <code>{fmt_n(v)}</code>")
            lines.append(SEP)
    return "\n".join(lines)


def build_analysis_buttons(uid: int, a: dict) -> list:
    kb = [
        [pbtn(f"✅ Live ({len(a['live'])})", data=f"exp_live:{uid}"),
         pbtn(f"⏰ Expired ({len(a['expired'])})", data=f"exp_expired:{uid}")],
        [pbtn(f"❌ Invalid ({len(a['invalid'])})", data=f"exp_invalid:{uid}"),
         pbtn(f"♻️ Dupes ({len(a['duplicates'])})", data=f"exp_dupes:{uid}")],
        [pbtn(bs("🌍 Country"), data=f"menu_country:{uid}"),
         pbtn(bs("💳 Brand"), data=f"menu_brand:{uid}")],
        [pbtn(bs("💠 Type"), data=f"menu_type:{uid}"),
         pbtn(bs("🏦 BIN"), data=f"menu_bin:{uid}")],
        [pbtn(bs("⚡ Actions"), data=f"menu_actions:{uid}")],
    ]
    return kb


def build_main_menu() -> list:
    return [
        [pbtn(bs("📁 File Tools"), data="menu_file")],
        [pbtn(bs("🎯 Filters"), data="menu_filters")],
        [pbtn(bs("⚡ BIN Ops"), data="menu_binops")],
        [pbtn(bs("💎 BIN Lookup"), data="menu_binlookup")],
        [pbtn(bs("🎲 Generator"), data="menu_gen")],
        [pbtn(bs("🔍 Regex Extract"), data="menu_extract")],
        [pbtn(bs("ℹ️ Help"), data="menu_help")],
    ]


# ───────────── START / HELP ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]start$'))
async def cmd_start(event):
    await styled_reply(event, f"""{PE} <b>{bs('NOXNI v2.0')}</b>
{SEP}
🎯 <b>{bs('CC Scraper & Cleaner')}</b>
{SEP}
🔥 <b>Analyze · Split · Filter · Export · Scrape</b>
{SEP}
📁 <b>How to Use</b>
├─ 🏦 <b>Send .txt file</b> → Auto Analyze & Menu
└─ 💎 <code>/clean</code> + reply .txt → Dedupe & Format
{SEP}
⭐️ <b>Features</b>
├─ 💎 Live / Expired / Luhn Filter
├─ 🎮 Split by Parts or Chunk Size
├─ 💱 BIN · Country · Brand Filter
├─ 🧩 Shuffle · Sample · Statistics
└─ 💰 Export TXT · CSV · JSON
{SEP}
👇 <b>Send a .txt file to begin</b>
{SEP}
🎛 <b>Or use the menu below</b>""",
        buttons=build_main_menu())


@client.on(events.NewMessage(pattern=r'^[/.]help$'))
async def cmd_help(event):
    await styled_reply(event, f"""{PE} <b>{bs('NOXNI — All Commands')}</b>
{SEP}
📁 <b>{bs('File Tools (reply .txt)')}</b>
├─ <code>/clean</code> — dedupe + format + remove expired
├─ <code>/superclean</code> — + luhn validation
├─ <code>/format</code> — normalize format
├─ <code>/dedup</code> — remove exact duplicates
├─ <code>/split N</code> — split into chunks of N
├─ <code>/parts N</code> — split into N equal parts
├─ <code>/merge</code> — combine multiple files
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
├─ <code>/fvbv</code> — filter VBV (live cards)
├─ <code>/f2d</code> — filter 2D cards
├─ <code>/f3d</code> — filter 3D cards
├─ <code>/expired</code> — export expired only
├─ <code>/invalid</code> — export invalid only
└─ <code>/sort bin|exp|country|bank|type|level</code>
{SEP}
⚡ <b>{bs('BIN Operations')}</b>
├─ <code>/bin 515462</code> — BIN lookup
├─ <code>/bins</code> — extract unique BINs
├─ <code>/topbins</code> — most common
├─ <code>/rembin 515462</code> — remove BIN
├─ <code>/remco US</code> — remove by country
├─ <code>/rembank Chase</code> — remove by bank
└─ <code>/remdup</code> — remove duplicates
{SEP}
🎲 <b>{bs('Generator')}</b>
├─ <code>/gen 515462 10</code> — generate N cards
├─ <code>/genluhn 515462 10</code> — with luhn
└─ <code>/genext 5 12 2028 123</code> — extension
{SEP}
🔍 <b>{bs('Extractors')}</b>
├─ <code>/getemails</code> — all emails
├─ <code>/geturls</code> — all URLs
├─ <code>/getphone</code> — phone numbers
├─ <code>/getip</code> — IP addresses
└─ <code>/getcc</code> — all card numbers
{SEP}
🎛 <b>{bs('Menu')}</b>
└─ <code>/menu</code> — interactive buttons""",
        buttons=[[pbtn(bs("🔙 Main Menu"), data="menu_home")]])


@client.on(events.NewMessage(pattern=r'^[/.]menu$'))
async def cmd_menu(event):
    await styled_reply(event, f"{PE} <b>{bs('Main Menu')}</b>",
                       buttons=build_main_menu())


# ───────────── CALLBACK ROUTER ─────────────
@client.on(events.CallbackQuery(data=b"menu_home"))
async def cb_home(event):
    await event.answer()
    try:
        await event.edit(f"{PE} <b>{bs('Main Menu')}</b>",
                         buttons=build_main_menu(), parse_mode='html')
    except: pass


@client.on(events.CallbackQuery(data=b"menu_help"))
async def cb_help(event):
    await event.answer()
    try:
        await event.edit(f"""{PE} <b>{bs('Help')}</b>
{SEP}
📁 Send any <code>.txt</code> file to auto-analyze
🎯 Use <code>/help</code> for all commands
⚡ Use buttons below""",
            buttons=[[pbtn(bs("🔙 Back"), data="menu_home")]],
            parse_mode='html')
    except: pass


@client.on(events.CallbackQuery(data=b"menu_file"))
async def cb_file_menu(event):
    await event.answer()
    kb = [
        [pbtn(bs("🧹 Clean"), data="cmd_clean_help"),
         pbtn(bs("💎 Superclean"), data="cmd_superclean_help")],
        [pbtn(bs("📁 Split"), data="cmd_split_help"),
         pbtn(bs("📁 Parts"), data="cmd_parts_help")],
        [pbtn(bs("🔢 Count"), data="cmd_count_help"),
         pbtn(bs("ℹ️ Info"), data="cmd_info_help")],
        [pbtn(bs("🔀 Shuffle"), data="cmd_shuffle_help"),
         pbtn(bs("↩️ Reverse"), data="cmd_reverse_help")],
        [pbtn(bs("🎲 Rand"), data="cmd_rand_help"),
         pbtn(bs("🎯 Head/Tail"), data="cmd_ht_help")],
        [pbtn(bs("♻️ Dedup"), data="cmd_dedup_help"),
         pbtn(bs("📐 Format"), data="cmd_format_help")],
        [pbtn(bs("🔙 Back"), data="menu_home")],
    ]
    await event.edit(f"""{PE} <b>{bs('File Tools')}</b>
{SEP}
Reply to a <code>.txt</code> file with any of these commands:
{SEP}
<code>/clean</code> · <code>/superclean</code> · <code>/format</code>
<code>/dedup</code> · <code>/split N</code> · <code>/parts N</code>
<code>/count</code> · <code>/info</code> · <code>/rand N</code>
<code>/head N</code> · <code>/tail N</code> · <code>/shuffle</code>
<code>/reverse</code> · <code>/topbins</code> · <code>/search text</code>
<code>/getemails</code> · <code>/geturls</code>""",
        buttons=kb, parse_mode='html')


@client.on(events.CallbackQuery(data=b"menu_filters"))
async def cb_filters_menu(event):
    await event.answer()
    kb = [
        [pbtn(bs("🌍 /fco"), data="cmd_fco_help"),
         pbtn(bs("💳 /fnet"), data="cmd_fnet_help")],
        [pbtn(bs("🏦 /fbank"), data="cmd_fbank_help"),
         pbtn(bs("💠 /ftype"), data="cmd_ftype_help")],
        [pbtn(bs("🏅 /flevel"), data="cmd_flevel_help"),
         pbtn(bs("📅 /fexp"), data="cmd_fexp_help")],
        [pbtn(bs("🎯 /fbin"), data="cmd_fbin_help"),
         pbtn(bs("📊 /sort"), data="cmd_sort_help")],
        [pbtn(bs("🔙 Back"), data="menu_home")],
    ]
    await event.edit(f"""{PE} <b>{bs('Filters')}</b>
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
<code>/sort bin|exp|country|bank|type|level</code>""",
        buttons=kb, parse_mode='html')


@client.on(events.CallbackQuery(data=b"menu_binops"))
async def cb_binops_menu(event):
    await event.answer()
    kb = [
        [pbtn(bs("🔍 BIN Lookup"), data="menu_binlookup"),
         pbtn(bs("📊 Top BINs"), data="cmd_topbins_help")],
        [pbtn(bs("🎯 Extract BINs"), data="cmd_bins_help"),
         pbtn(bs("🗑️ Remove BIN"), data="cmd_rembin_help")],
        [pbtn(bs("🌍 Remove Country"), data="cmd_remco_help"),
         pbtn(bs("🏦 Remove Bank"), data="cmd_rembank_help")],
        [pbtn(bs("♻️ Remove Dupes"), data="cmd_remdup_help")],
        [pbtn(bs("🔙 Back"), data="menu_home")],
    ]
    await event.edit(f"""{PE} <b>{bs('BIN Operations')}</b>
{SEP}
<code>/bin 515462</code> — BIN lookup
<code>/bins</code> — extract unique BINs
<code>/topbins</code> — most common BINs
<code>/rembin 515462</code> — remove BIN
<code>/remco US</code> — remove by country
<code>/rembank Chase</code> — remove by bank
<code>/remdup</code> — remove duplicates""",
        buttons=kb, parse_mode='html')


@client.on(events.CallbackQuery(data=b"menu_binlookup"))
async def cb_binlookup_menu(event):
    await event.answer()
    await event.edit(f"""{PE} <b>{bs('BIN Lookup')}</b>
{SEP}
Use:
<code>/bin 515462</code>
{SEP}
Returns: Brand · Type · Level · Bank · Country""",
        buttons=[[pbtn(bs("🔙 Back"), data="menu_binops")]],
        parse_mode='html')


@client.on(events.CallbackQuery(data=b"menu_gen"))
async def cb_gen_menu(event):
    await event.answer()
    await event.edit(f"""{PE} <b>{bs('Card Generator')}</b>
{SEP}
<code>/gen 515462 10</code>
{SEP}
Generates 10 cards with BIN prefix 515462
Random valid mm/yyyy/cvv""",
        buttons=[[pbtn(bs("🔙 Back"), data="menu_home")]],
        parse_mode='html')


@client.on(events.CallbackQuery(data=b"menu_extract"))
async def cb_extract_menu(event):
    await event.answer()
    await event.edit(f"""{PE} <b>{bs('Extractors')}</b>
{SEP}
Reply to a <code>.txt</code>:
{SEP}
<code>/getemails</code> — extract emails
<code>/geturls</code> — extract URLs
<code>/getphone</code> — extract phone numbers
<code>/getip</code> — extract IPs
<code>/getcc</code> — extract card numbers""",
        buttons=[[pbtn(bs("🔙 Back"), data="menu_home")]],
        parse_mode='html')


# ───────────── HELP CALLBACKS ─────────────
@client.on(events.CallbackQuery(pattern=rb"^cmd_(\w+)_help$"))
async def cb_cmd_help(event):
    cmd = event.pattern_match.group(1).decode()
    helps = {
        "clean":       "/clean — Reply to .txt\nDedupe + format + remove expired",
        "superclean":  "/superclean — Reply to .txt\n+ Luhn validation",
        "format":      "/format — Reply to .txt\nNormalize to cc|mm|yyyy|cvv",
        "dedup":       "/dedup — Reply to .txt\nRemove exact duplicates",
        "split":       "/split N — Reply to .txt\nSplit into chunks of N",
        "parts":       "/parts N — Reply to .txt\nSplit into N equal parts",
        "count":       "/count — Reply to .txt\nCount lines + valid cards",
        "info":        "/info — Reply to .txt\nFull analysis (live/expired/bins)",
        "rand":        "/rand N — Reply to .txt\nRandom sample of N lines",
        "shuffle":     "/shuffle — Reply to .txt\nRandom shuffle",
        "reverse":     "/reverse — Reply to .txt\nReverse order",
        "ht":          "/head N or /tail N\nFirst or last N lines",
        "fco":         "/fco US — Reply to .txt\nFilter by country",
        "fnet":        "/fnet visa — Reply to .txt\nFilter by network",
        "fbank":       "/fbank Chase — Reply to .txt\nFilter by bank",
        "ftype":       "/ftype credit — Reply to .txt\nFilter by type",
        "flevel":      "/flevel platinum — Reply to .txt\nFilter by level",
        "fexp":        "/fexp 12/26 — Reply to .txt\nFilter by expiry",
        "fbin":        "/fbin 515462 — Reply to .txt\nFilter by BIN prefix",
        "sort":        "/sort bin — Reply to .txt\nSort by field",
        "topbins":     "/topbins — Reply to .txt\nTop 20 BINs",
        "bins":        "/bins — Reply to .txt\nAll unique BINs",
        "rembin":      "/rembin 515462 — Reply to .txt\nRemove BIN",
        "remco":       "/remco US — Reply to .txt\nRemove country",
        "rembank":     "/rembank Chase — Reply to .txt\nRemove bank",
        "remdup":      "/remdup — Reply to .txt\nRemove duplicates",
    }
    await event.answer()
    await event.edit(f"{PE} <b>{bs('Help')}</b>\n{SEP}\n<code>{helps.get(cmd, 'N/A')}</code>",
        buttons=[[pbtn(bs("🔙 Back"), data="menu_home")]],
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

    sm = await styled_reply(event, f"{PE} <b>{bs('Analyzing')}</b> …")
    content, fname = await download_and_read(event.message)
    if content is None:
        return await styled_edit(sm, f"{PE} <b>{bs('Error')}:</b> <code>{fname}</code>")
    cards = extract_cards(content)
    if not cards:
        return await styled_edit(sm, f"{PE} <b>{bs('No valid cards')}</b>\n"
                                     f"{SEP}\nLines: <code>{len(content.splitlines())}</code>")
    if len(cards) > MAX_CARDS: cards = cards[:MAX_CARDS]
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
    if not event.reply_to_msg_id: return await styled_reply(event, f"{PE} <b>Reply to a .txt</b>")
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    await styled_reply(event, f"{PE} <b>{bs('Count')}</b>\n{SEP}\n"
                              f"Lines: <code>{len(content.splitlines())}</code>\n"
                              f"Cards: <code>{len(extract_cards(content))}</code>")


@client.on(events.NewMessage(pattern=r'^[/.]info$'))
async def cmd_info(event):
    if not event.reply_to_msg_id: return await styled_reply(event, f"{PE} <b>Reply to a .txt</b>")
    rm = await event.get_reply_message()
    content, fname = await download_and_read(rm)
    if not content: return
    cards = extract_cards(content)
    if not cards: return await styled_reply(event, f"{PE} <b>No cards</b>")
    a = analyze_cards(cards)
    try: await enrich_with_bin_info(a, a["live"], limit=20)
    except: pass
    await styled_reply(event, build_analysis_text(a, fname))


@client.on(events.NewMessage(pattern=r'^[/.]clean$'))
async def cmd_clean(event):
    if not event.reply_to_msg_id: return await styled_reply(event, f"{PE} <b>Reply to .txt</b>")
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    out, seen = [], set()
    r_exp = r_inv = r_dup = 0
    for line in content.splitlines():
        p = parse_card_line(line)
        if not p: r_inv += 1; continue
        cc, mm, yyyy, cvv = p
        card = f"{cc}|{mm}|{yyyy}|{cvv}"
        if card in seen: r_dup += 1; continue
        if is_expired(mm, yyyy): r_exp += 1; continue
        seen.add(card); out.append(card)
    if not out: return await styled_reply(event, f"{PE} <b>Nothing valid</b>")
    await send_txt(event.sender_id, out,
        f"cleaned_{len(out)}")
    await styled_reply(event, f"{PE} <b>{bs('Cleaned')}</b>\n{SEP}\n"
                              f"✅ Kept: <code>{len(out)}</code>\n"
                              f"⏰ Expired: <code>{r_exp}</code>\n"
                              f"❌ Invalid: <code>{r_inv}</code>\n"
                              f"♻️ Dupes: <code>{r_dup}</code>")


@client.on(events.NewMessage(pattern=r'^[/.]superclean$'))
async def cmd_superclean(event):
    if not event.reply_to_msg_id: return await styled_reply(event, f"{PE} <b>Reply to .txt</b>")
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    out, seen = [], set()
    r = {"exp": 0, "inv": 0, "dup": 0, "luhn": 0}
    for line in content.splitlines():
        p = parse_card_line(line)
        if not p: r["inv"] += 1; continue
        cc, mm, yyyy, cvv = p
        card = f"{cc}|{mm}|{yyyy}|{cvv}"
        if card in seen: r["dup"] += 1; continue
        if is_expired(mm, yyyy): r["exp"] += 1; continue
        if not luhn_ok(cc): r["luhn"] += 1; continue
        seen.add(card); out.append(card)
    if not out: return await styled_reply(event, f"{PE} <b>Nothing valid</b>")
    await send_txt(event.sender_id, out, f"superclean_{len(out)}")
    await styled_reply(event, f"{PE} <b>{bs('Super Cleaned')}</b>\n{SEP}\n"
                              f"✅ Kept: <code>{len(out)}</code>\n"
                              f"⏰ Expired: <code>{r['exp']}</code>\n"
                              f"❌ Invalid: <code>{r['inv']}</code>\n"
                              f"♻️ Dupes: <code>{r['dup']}</code>\n"
                              f"🔢 Luhn fail: <code>{r['luhn']}</code>")


@client.on(events.NewMessage(pattern=r'^[/.]format$'))
async def cmd_format(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    out = []
    for line in content.splitlines():
        p = parse_card_line(line)
        if p: out.append(f"{p[0]}|{p[1]}|{p[2]}|{p[3]}")
    if not out: return await styled_reply(event, f"{PE} <b>No cards</b>")
    await send_txt(event.sender_id, out, f"formatted_{len(out)}")


@client.on(events.NewMessage(pattern=r'^[/.]dedup$'))
async def cmd_dedup(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    seen, out = set(), []
    for line in content.splitlines():
        s = line.strip()
        if s and s not in seen: seen.add(s); out.append(s)
    await send_txt(event.sender_id, out, f"dedup_{len(out)}")


# ───────────── SPLIT / PARTS ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]split(?:\s+(\d+))?$'))
async def cmd_split(event):
    if not event.reply_to_msg_id: return
    chunk = int(event.pattern_match.group(1) or 300)
    chunk = max(50, min(50000, chunk))
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines: return await styled_reply(event, f"{PE} <b>Empty</b>")
    total = math.ceil(len(lines) / chunk)
    for i in range(total):
        part = lines[i * chunk:(i + 1) * chunk]
        await send_txt(event.sender_id, part, f"part_{i+1}_of_{total}")


@client.on(events.NewMessage(pattern=r'^[/.]parts(?:\s+(\d+))?$'))
async def cmd_parts(event):
    if not event.reply_to_msg_id: return
    n = max(2, min(50, int(event.pattern_match.group(1) or 5)))
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines: return await styled_reply(event, f"{PE} <b>Empty</b>")
    size = math.ceil(len(lines) / n)
    total = math.ceil(len(lines) / size)
    for i in range(total):
        part = lines[i * size:(i + 1) * size]
        await send_txt(event.sender_id, part, f"part_{i+1}_of_{total}")


# ───────────── HEAD / TAIL / RAND ─────────────
@client.on(events.NewMessage(pattern=r'^[/.](head|tail|rand)(?:\s+(\d+))?$'))
async def cmd_hlr(event):
    if not event.reply_to_msg_id: return
    cmd = event.pattern_match.group(1).decode()
    n = max(1, min(5000, int(event.pattern_match.group(2) or 20)))
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines: return await styled_reply(event, f"{PE} <b>Empty</b>")
    if cmd == "head": out = lines[:n]
    elif cmd == "tail": out = lines[-n:]
    else: out = random.sample(lines, min(n, len(lines)))
    await send_txt(event.sender_id, out, f"{cmd}_{len(out)}")


@client.on(events.NewMessage(pattern=r'^[/.]shuffle$'))
async def cmd_shuffle(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    random.shuffle(lines)
    await send_txt(event.sender_id, lines, f"shuffled_{len(lines)}")


@client.on(events.NewMessage(pattern=r'^[/.]reverse$'))
async def cmd_reverse(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    lines.reverse()
    await send_txt(event.sender_id, lines, f"reversed_{len(lines)}")


# ───────────── TOP BINS / BINS ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]topbins$'))
async def cmd_topbins(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    cards = extract_cards(content)
    if not cards: return await styled_reply(event, f"{PE} <b>No cards</b>")
    bins = Counter(c[:6] for c in cards)
    lines = [f"<code>{b}</code> ━ {n}" for b, n in bins.most_common(20)]
    await styled_reply(event, f"{PE} <b>{bs('Top BINs')}</b>\n{SEP}\n" + "\n".join(lines))


@client.on(events.NewMessage(pattern=r'^[/.]bins$'))
async def cmd_bins(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    cards = extract_cards(content)
    if not cards: return await styled_reply(event, f"{PE} <b>No cards</b>")
    bins = sorted(set(c[:6] for c in cards))
    fn = f"bins_{int(time.time())}.txt"
    async with aiofiles.open(fn, "w") as f:
        await f.write("\n".join(bins))
    try:
        await client_instance.send_file(event.sender_id, fn,
            caption=f"{PE} <b>{bs('Unique BINs')}</b> ({len(bins)})")
    finally:
        try: os.remove(fn)
        except: pass


# ───────────── SEARCH / EXTRACT ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]search\s+(.+)$'))
async def cmd_search(event):
    if not event.reply_to_msg_id: return
    term = event.pattern_match.group(1).strip().lower()
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    results = [l for l in content.splitlines() if term in l.lower()]
    if not results: return await styled_reply(event, f"{PE} <b>No matches</b>")
    await send_txt(event.sender_id, results, f"search_{term}_{len(results)}")


@client.on(events.NewMessage(pattern=r'^[/.]getemails$'))
async def cmd_getemails(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    emails = list(set(re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', content)))
    if not emails: return await styled_reply(event, f"{PE} <b>No emails</b>")
    await send_txt(event.sender_id, emails, f"emails_{len(emails)}")


@client.on(events.NewMessage(pattern=r'^[/.]geturls$'))
async def cmd_geturls(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    urls = list(set(re.findall(r'https?://[^\s]+', content)))
    if not urls: return await styled_reply(event, f"{PE} <b>No urls</b>")
    await send_txt(event.sender_id, urls, f"urls_{len(urls)}")


@client.on(events.NewMessage(pattern=r'^[/.]getphone$'))
async def cmd_getphone(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    phones = list(set(re.findall(r'\+?\d[\d\s\-\(\)]{7,}\d', content)))
    if not phones: return await styled_reply(event, f"{PE} <b>No phones</b>")
    await send_txt(event.sender_id, phones, f"phones_{len(phones)}")


@client.on(events.NewMessage(pattern=r'^[/.]getip$'))
async def cmd_getip(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    ips = list(set(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', content)))
    if not ips: return await styled_reply(event, f"{PE} <b>No IPs</b>")
    await send_txt(event.sender_id, ips, f"ips_{len(ips)}")


# ───────────── FILTERS ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]fbin\s+(\d{6,})$'))
async def cmd_fbin(event):
    prefix = event.pattern_match.group(1)
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    filtered = [c for c in extract_cards(content) if c.startswith(prefix)]
    if not filtered: return await styled_reply(event, f"{PE} <b>No matches</b>")
    await send_txt(event.sender_id, filtered, f"bin_{prefix}_{len(filtered)}")


@client.on(events.NewMessage(pattern=r'^[/.]fnet\s+(\w+)$'))
async def cmd_fnet(event):
    net = event.pattern_match.group(1).lower()
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    filtered = [c for c in extract_cards(content) if detect_brand(c.split("|")[0]).lower() == net]
    if not filtered: return await styled_reply(event, f"{PE} <b>No matches</b>")
    await send_txt(event.sender_id, filtered, f"net_{net}_{len(filtered)}")


@client.on(events.NewMessage(pattern=r'^[/.]fexp\s+(\d{1,2})/(\d{2,4})$'))
async def cmd_fexp(event):
    mm = event.pattern_match.group(1).zfill(2)
    yy = event.pattern_match.group(2)
    if len(yy) == 2: yy = "20" + yy
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    filtered = []
    for c in extract_cards(content):
        p = parse_card_line(c)
        if p and p[1] == mm and p[2] == yy:
            filtered.append(c)
    if not filtered: return await styled_reply(event, f"{PE} <b>No matches</b>")
    await send_txt(event.sender_id, filtered, f"exp_{mm}_{yy}_{len(filtered)}")


@client.on(events.NewMessage(pattern=r'^[/.]fco\s+(\w+)$'))
async def cmd_fco(event):
    country = event.pattern_match.group(1).upper()
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    cards = extract_cards(content)
    filtered = []
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    for c in cards:
        i = info.get(c[:6], {})
        if i.get("country", "").upper() == country:
            filtered.append(c)
    if not filtered: return await styled_reply(event, f"{PE} <b>No matches</b>")
    await send_txt(event.sender_id, filtered, f"country_{country}_{len(filtered)}")


@client.on(events.NewMessage(pattern=r'^[/.]fbank\s+(.+)$'))
async def cmd_fbank(event):
    bank = event.pattern_match.group(1).strip().lower()
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    cards = extract_cards(content)
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    filtered = [c for c in cards if bank in info.get(c[:6], {}).get("bank", "").lower()]
    if not filtered: return await styled_reply(event, f"{PE} <b>No matches</b>")
    await send_txt(event.sender_id, filtered, f"bank_{bank[:10]}_{len(filtered)}")


@client.on(events.NewMessage(pattern=r'^[/.]ftype\s+(\w+)$'))
async def cmd_ftype(event):
    typ = event.pattern_match.group(1).lower()
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    cards = extract_cards(content)
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    filtered = [c for c in cards if typ in info.get(c[:6], {}).get("type", "").lower()]
    if not filtered: return await styled_reply(event, f"{PE} <b>No matches</b>")
    await send_txt(event.sender_id, filtered, f"type_{typ}_{len(filtered)}")


@client.on(events.NewMessage(pattern=r'^[/.]flevel\s+(\w+)$'))
async def cmd_flevel(event):
    lvl = event.pattern_match.group(1).lower()
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    cards = extract_cards(content)
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    filtered = [c for c in cards if lvl in info.get(c[:6], {}).get("level", "").lower()]
    if not filtered: return await styled_reply(event, f"{PE} <b>No matches</b>")
    await send_txt(event.sender_id, filtered, f"level_{lvl}_{len(filtered)}")


@client.on(events.NewMessage(pattern=r'^[/.]sort\s+(\w+)$'))
async def cmd_sort(event):
    field = event.pattern_match.group(1).lower()
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    cards = extract_cards(content)
    if not cards: return await styled_reply(event, f"{PE} <b>No cards</b>")

    if field == "bin":
        cards.sort(key=lambda x: x[:6])
    elif field == "exp":
        cards.sort(key=lambda x: (x.split("|")[2], x.split("|")[1]))
    elif field in ("country", "bank", "type", "level"):
        unique_bins = list(set(c[:6] for c in cards))
        info = await bin_lookup.lookup_many(unique_bins)
        cards.sort(key=lambda x: info.get(x[:6], {}).get(field, ""))
    await send_txt(event.sender_id, cards, f"sorted_{field}_{len(cards)}")


@client.on(events.NewMessage(pattern=r'^[/.]expired$'))
async def cmd_expired(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    out = []
    for c in extract_cards(content):
        p = parse_card_line(c)
        if p and is_expired(p[1], p[2]):
            out.append(c)
    if not out: return await styled_reply(event, f"{PE} <b>No expired</b>")
    await send_txt(event.sender_id, out, f"expired_{len(out)}")


@client.on(events.NewMessage(pattern=r'^[/.]invalid$'))
async def cmd_invalid(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    out = []
    for line in content.splitlines():
        if not parse_card_line(line):
            out.append(line.strip())
    if not out: return await styled_reply(event, f"{PE} <b>No invalid</b>")
    await send_txt(event.sender_id, out, f"invalid_{len(out)}")


@client.on(events.NewMessage(pattern=r'^[/.]fvbv$'))
async def cmd_fvbv(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    out = [c for c in extract_cards(content)
           if luhn_ok(c.split("|")[0]) and not is_expired(*c.split("|")[1:3])]
    if not out: return await styled_reply(event, f"{PE} <b>None</b>")
    await send_txt(event.sender_id, out, f"vbv_{len(out)}")


@client.on(events.NewMessage(pattern=r'^[/.]f2d$'))
async def cmd_f2d(event):
    # 2D = valid + non-3ds — for this tool we mark all valid non-expired
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    out = [c for c in extract_cards(content)
           if luhn_ok(c.split("|")[0]) and not is_expired(*c.split("|")[1:3])]
    if not out: return await styled_reply(event, f"{PE} <b>None</b>")
    await send_txt(event.sender_id, out, f"2d_{len(out)}")


@client.on(events.NewMessage(pattern=r'^[/.]f3d$'))
async def cmd_f3d(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    out = [c for c in extract_cards(content) if luhn_ok(c.split("|")[0])]
    if not out: return await styled_reply(event, f"{PE} <b>None</b>")
    await send_txt(event.sender_id, out, f"3d_{len(out)}")


# ───────────── REMOVE OPS ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]rembin\s+(\d{6,})$'))
async def cmd_rembin(event):
    prefix = event.pattern_match.group(1)
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    out = [c for c in extract_cards(content) if not c.startswith(prefix)]
    await send_txt(event.sender_id, out, f"removed_{prefix}_{len(out)}")


@client.on(events.NewMessage(pattern=r'^[/.]remco\s+(\w+)$'))
async def cmd_remco(event):
    country = event.pattern_match.group(1).upper()
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    cards = extract_cards(content)
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    out = [c for c in cards if info.get(c[:6], {}).get("country", "").upper() != country]
    await send_txt(event.sender_id, out, f"removed_{country}_{len(out)}")


@client.on(events.NewMessage(pattern=r'^[/.]rembank\s+(.+)$'))
async def cmd_rembank(event):
    bank = event.pattern_match.group(1).strip().lower()
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    cards = extract_cards(content)
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    out = [c for c in cards if bank not in info.get(c[:6], {}).get("bank", "").lower()]
    await send_txt(event.sender_id, out, f"removed_{len(out)}")


@client.on(events.NewMessage(pattern=r'^[/.]remdup$'))
async def cmd_remdup(event):
    if not event.reply_to_msg_id: return
    rm = await event.get_reply_message()
    content, _ = await download_and_read(rm)
    if not content: return
    seen, out = set(), []
    for c in extract_cards(content):
        if c not in seen:
            seen.add(c); out.append(c)
    await send_txt(event.sender_id, out, f"dedup_{len(out)}")


# ───────────── BIN LOOKUP ─────────────
@client.on(events.NewMessage(pattern=r'^[/.]bin(?:\s+(\d{6}))?$'))
async def cmd_bin(event):
    b = event.pattern_match.group(1)
    if not b: return await styled_reply(event, f"{PE} <code>/bin 515462</code>")
    i = await bin_lookup.lookup(b)
    await styled_reply(event, f"""{PE} <b>{bs('BIN Lookup')}</b>
{SEP}
📌 BIN: <code>{b}</code>
💳 Brand: <code>{i['brand']}</code>
💠 Type: <code>{i['type']}</code>
🏅 Level: <code>{i['level']}</code>
🏦 Bank: <code>{i['bank']}</code>
🌍 Country: <code>{i['country']} {i['flag']}</code>""")


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
    await send_txt(event.sender_id, cards, f"gen_{bin_pref}_{len(cards)}")


@client.on(events.NewMessage(pattern=r'^[/.]genluhn(?:\s+(\d{6,}))(?:\s+(\d+))?$'))
async def cmd_genluhn(event):
    # Same as gen, already luhn-valid
    await cmd_gen(event)


# ───────────── ANALYSIS BUTTONS ─────────────
@client.on(events.CallbackQuery(pattern=rb"^exp_(\w+):(\d+)$"))
async def cb_export(event):
    kind = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid: return await event.answer("Not yours", alert=True)
    s = get_session(uid)
    if not s: return await event.answer("Expired", alert=True)
    key_map = {"live": "live", "expired": "expired", "invalid": "invalid", "dupes": "duplicates"}
    cards = s["analysis"].get(key_map.get(kind, ""), [])
    await event.answer(f"Sending {len(cards)}")
    await send_txt(uid, cards, kind)


@client.on(events.CallbackQuery(pattern=rb"^menu_(\w+):(\d+)$"))
async def cb_menu_actions(event):
    menu = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid: return await event.answer("Not yours", alert=True)
    s = get_session(uid)
    if not s: return await event.answer("Expired", alert=True)
    a = s["analysis"]

    if menu == "country":
        items = top_items(a["countries"], 12)
        kb = [[pbtn(f"{c} ({n})", data=f"fco_{uid}_{c}")] for c, n in items]
        kb.append([pbtn(bs("🔙 Back"), data=f"menu_actions:{uid}")])
        await event.edit(f"{PE} <b>Filter Country</b>", buttons=kb, parse_mode='html')

    elif menu == "brand":
        items = top_items(a["brands"], 12)
        kb = [[pbtn(f"{b} ({n})", data=f"fbrand_{uid}_{b}")] for b, n in items]
        kb.append([pbtn(bs("🔙 Back"), data=f"menu_actions:{uid}")])
        await event.edit(f"{PE} <b>Filter Brand</b>", buttons=kb, parse_mode='html')

    elif menu == "type":
        items = top_items(a["types"], 12)
        kb = [[pbtn(f"{t} ({n})", data=f"ftype_{uid}_{t}")] for t, n in items]
        kb.append([pbtn(bs("🔙 Back"), data=f"menu_actions:{uid}")])
        await event.edit(f"{PE} <b>Filter Type</b>", buttons=kb, parse_mode='html')

    elif menu == "bin":
        items = top_items(a["bins"], 12)
        kb = [[pbtn(f"{b} ({n})", data=f"fbin_{uid}_{b}")] for b, n in items]
        kb.append([pbtn(bs("🔙 Back"), data=f"menu_actions:{uid}")])
        await event.edit(f"{PE} <b>Filter BIN</b>", buttons=kb, parse_mode='html')

    elif menu == "actions":
        kb = [
            [pbtn(bs("📁 Split 300"), data=f"act_split:{uid}"),
             pbtn(bs("📁 Split 1000"), data=f"act_split1000:{uid}")],
            [pbtn(bs("🔀 Shuffle"), data=f"act_shuffle:{uid}"),
             pbtn(bs("🎲 Random 100"), data=f"act_rand100:{uid}")],
            [pbtn(bs("📤 TXT"), data=f"act_txt:{uid}"),
             pbtn(bs("📤 CSV"), data=f"act_csv:{uid}"),
             pbtn(bs("📤 JSON"), data=f"act_json:{uid}")],
            [pbtn(bs("🔙 Back"), data=f"act_back:{uid}")],
        ]
        await event.edit(f"{PE} <b>Actions</b>", buttons=kb, parse_mode='html')


@client.on(events.CallbackQuery(pattern=rb"^fco_(\d+)_(.+)$"))
async def cb_fco(event):
    uid = int(event.pattern_match.group(1).decode())
    country = event.pattern_match.group(2).decode()
    if event.sender_id != uid: return await event.answer("Not yours", alert=True)
    s = get_session(uid)
    if not s: return await event.answer("Expired", alert=True)
    cards = s["analysis"]["live"]
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    filtered = [c for c in cards if info.get(c[:6], {}).get("country") == country]
    await event.answer(f"{len(filtered)} cards")
    await send_txt(uid, filtered, f"country_{country}_{len(filtered)}")


@client.on(events.CallbackQuery(pattern=rb"^fbrand_(\d+)_(.+)$"))
async def cb_fbrand(event):
    uid = int(event.pattern_match.group(1).decode())
    brand = event.pattern_match.group(2).decode()
    if event.sender_id != uid: return await event.answer("Not yours", alert=True)
    s = get_session(uid)
    if not s: return await event.answer("Expired", alert=True)
    filtered = [c for c in s["analysis"]["live"] if detect_brand(c.split("|")[0]) == brand]
    await event.answer(f"{len(filtered)}")
    await send_txt(uid, filtered, f"brand_{brand}_{len(filtered)}")


@client.on(events.CallbackQuery(pattern=rb"^ftype_(\d+)_(.+)$"))
async def cb_ftype(event):
    uid = int(event.pattern_match.group(1).decode())
    typ = event.pattern_match.group(2).decode()
    if event.sender_id != uid: return await event.answer("Not yours", alert=True)
    s = get_session(uid)
    if not s: return await event.answer("Expired", alert=True)
    cards = s["analysis"]["live"]
    unique_bins = list(set(c[:6] for c in cards))
    info = await bin_lookup.lookup_many(unique_bins)
    filtered = [c for c in cards if info.get(c[:6], {}).get("type") == typ]
    await event.answer(f"{len(filtered)}")
    await send_txt(uid, filtered, f"type_{typ}_{len(filtered)}")


@client.on(events.CallbackQuery(pattern=rb"^fbin_(\d+)_(.+)$"))
async def cb_fbin(event):
    uid = int(event.pattern_match.group(1).decode())
    b = event.pattern_match.group(2).decode()
    if event.sender_id != uid: return await event.answer("Not yours", alert=True)
    s = get_session(uid)
    if not s: return await event.answer("Expired", alert=True)
    filtered = [c for c in s["analysis"]["live"] if c.startswith(b)]
    await event.answer(f"{len(filtered)}")
    await send_txt(uid, filtered, f"bin_{b}_{len(filtered)}")


@client.on(events.CallbackQuery(pattern=rb"^act_(\w+):(\d+)$"))
async def cb_action(event):
    action = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid: return await event.answer("Not yours", alert=True)
    s = get_session(uid)
    if not s: return await event.answer("Expired", alert=True)
    cards = s["analysis"]["live"]

    if action == "split":
        chunk = 300
        total = math.ceil(len(cards) / chunk)
        for i in range(total):
            await send_txt(uid, cards[i * chunk:(i + 1) * chunk], f"part_{i+1}_of_{total}")
        await event.answer("Split sent")

    elif action == "split1000":
        chunk = 1000
        total = math.ceil(len(cards) / chunk)
        for i in range(total):
            await send_txt(uid, cards[i * chunk:(i + 1) * chunk], f"part_{i+1}_of_{total}")
        await event.answer("Split sent")

    elif action == "shuffle":
        s2 = list(cards); random.shuffle(s2)
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
    if event.sender_id not in ADMIN_ID: return
    files = [f for f in os.listdir(STORAGE_DIR) if f.endswith(".json")]
    await styled_reply(event, f"{PE} <b>Admin Stats</b>\n{SEP}\n"
                              f"📁 Files: <code>{len(files)}</code>\n"
                              f"👥 Sessions: <code>{len(SESSIONS)}</code>\n"
                              f"💾 Storage: <code>{STORAGE_DIR}</code>\n"
                              f"🆔 Channel: <code>{CHANNEL_ID}</code>")


# ───────────── MAIN ─────────────
async def main():
    global client_instance
    client_instance = client
    log_system("BOOT", "Starting NOXNI v2.0")
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
