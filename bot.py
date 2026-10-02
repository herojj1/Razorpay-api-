# =============================================================================
# NOVA Finder — Shopify Site Search Bot (v2.1.0)
# =============================================================================
# v2.1.0:
#   - Wired to shopify-fetcher.kamalxd.workers.dev (correct params)
#   - Accepts custom domains (not just .myshopify.com)
#   - Multi-keyword sweep to build big pools
#   - Buttons fixed
# =============================================================================

import os
import re
import json
import time
import random
import logging
import asyncio
from datetime import datetime
from urllib.parse import quote
from typing import Optional

import aiohttp
import aiofiles
from telethon import TelegramClient, events, Button
from telethon.errors import FloodWaitError
from telethon.tl.types import MessageEntityCustomEmoji
from telethon.extensions import html as thtml


# ====================== LOGGING ======================
log = logging.getLogger("FINDER")
log.setLevel(logging.INFO)
_fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                          datefmt='%Y-%m-%d %H:%M:%S')
_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(_fmt)
log.addHandler(_ch)

if not os.getenv("RAILWAY_ENVIRONMENT"):
    try:
        _fh = logging.FileHandler('nova_finder.log', encoding='utf-8')
        _fh.setLevel(logging.INFO)
        _fh.setFormatter(_fmt)
        log.addHandler(_fh)
    except Exception:
        pass


def log_user(uid, action, msg, level="info"):
    getattr(log, level, log.info)(f"[USER:{uid}] [{action}] {msg}")


def log_system(action, msg, level="info"):
    getattr(log, level, log.info)(f"[SYSTEM] [{action}] {msg}")


# ====================== BOLD SANS ======================
_BOLD_MAP = {}
for _i, _c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _BOLD_MAP[_c] = "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭"[_i]
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _BOLD_MAP[_c] = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇"[_i]
for _i, _c in enumerate("0123456789"):
    _BOLD_MAP[_c] = "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"[_i]


def bs(text):
    if not text:
        return text
    return "".join(_BOLD_MAP.get(c, c) for c in str(text))


# ====================== CONFIG ======================
API_ID    = int(os.getenv("FINDER_API_ID") or os.getenv("API_ID") or 33657928)
API_HASH  = os.getenv("FINDER_API_HASH") or os.getenv("API_HASH",
                    "a61fde61442113b9a65c699f7020d59a")
BOT_TOKEN = os.getenv("FINDER_BOT_TOKEN") or os.getenv("BOT_TOKEN", "8517366800:AAF3BgDkZ7tY5mWOMu3ztAx31NTVk7xzzcU")
ADMIN_ID  = [int(x) for x in (os.getenv("FINDER_ADMINS") or
                              "8871910561").split(",") if x.strip()]

ADMIN_FILE = "finder_admins.json"


def _load_admins():
    global ADMIN_ID
    try:
        if os.path.exists(ADMIN_FILE):
            with open(ADMIN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                merged = list(dict.fromkeys(
                    list(ADMIN_ID) + [int(x) for x in data
                                      if str(x).lstrip('-').isdigit()]
                ))
                ADMIN_ID.clear()
                ADMIN_ID.extend(merged)
    except Exception:
        pass


def _save_admins():
    try:
        with open(ADMIN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(ADMIN_ID), f, indent=2)
    except Exception:
        pass


BOT_BRAND = "NOVA FINDER"
OWNER_TAG = "@SUPERGREMLIN01"
DEV_LINE  = f"⌬ {bs('By')} <a href='https://t.me/{OWNER_TAG.lstrip('@')}'>{OWNER_TAG}</a>"
SEP       = "━━━━━━━━━━━━━━━━━"
PE        = "💎"

# Pool
SHOPIFY_POOL_FILE = "shopify_pool.txt"
SHOPIFY_META_FILE = "shopify_pool_meta.json"

# Source
SOURCE_FILE = "finder_source.json"
DEFAULT_SOURCE = os.getenv(
    "FINDER_SOURCE_URL",
    "https://shopify-fetcher.kamalxd.workers.dev"
)

# Optional alive-check API
CHECK_API_FILE = "finder_check_api.json"
CHECK_API_DEFAULT = os.getenv(
    "FINDER_CHECK_API",
    "https://web-production-e6929.up.railway.app/shopify"
)
CHECK_API_TIMEOUT = 60
TEST_CARD = "5154623245618097|03|2032|156"

# Search
RESULT_CHUNK = 30
MAX_PER_QUERY = 250          # worker returns up to 250 per call
MAX_KEYWORDS_PER_RUN = 40    # /shsweep cap

# Keyword seed list for /shsweep and /shsearch with no keyword
SEED_KEYWORDS = [
    "shirt", "tshirt", "hoodie", "jeans", "dress", "shoes", "sneakers",
    "socks", "jacket", "watch", "ring", "necklace", "bracelet", "earring",
    "bag", "wallet", "belt", "hat", "cap", "sunglasses", "phone case",
    "coffee", "tea", "mug", "candle", "soap", "skincare", "perfume",
    "lipstick", "makeup", "shampoo", "toy", "lego", "poster", "book",
    "notebook", "pen", "gift", "keychain", "sticker", "pillow", "bedding",
    "towel", "rug", "lamp", "vase", "plant", "succulent", "snack",
    "chocolate", "candy", "supplement", "vitamin", "protein", "yoga",
    "dumbbell", "bottle", "backpack", "charger", "headphone", "speaker",
    "keyboard", "mouse", "webcam", "drone", "camera", "toolkit",
]


# ====================== PREMIUM EMOJI ======================
PREMIUM_EMOJI_IDS = {
    "✅":"5278327121008167894","❌":"5785177332595561481","⚠️":"5420323339723881652",
    "🔥":"5039644681583985437","💎":"5427168083074628963","✨":"5040016479722931047",
    "🎯":"5039905162760553480","💰":"5039789890133296083","📊":"5042290883949495533",
    "👑":"5039727497143387500","🌐":"6321225560789877992","🔑":"5399885604701880145",
    "📁":"6026239398650056451","🗑":"5039614900280754969","📅":"6168242008277125889",
    "📥":"5443127283898405358","📤":"5445355530111437729","🔍":"5042302287087666158",
    "🔧":"5445059250382469069","💻":"5039579582764680065","📩":"5443127283898405358",
    "💡":"5042264341051605743","🛒":"5445224894386172410","🔙":"5445365692004071819",
    "🎁":"5039778134807806727","👥":"5443038326535759644","⚙️":"5445059250382469069",
    "📌":"5397782960512444700","📝":"5444889156792646660","🚀":"6174445826543191998",
    "🥇":"6179279816529814743","🏆":"6089185885289454318","💳":"5447453226498552490",
    "🎉":"5039778134807806727","⭐":"5042061201983407048","📡":"5447448489149625830",
}


def pe(text):
    if not text:
        return text
    out = text
    for emoji in sorted(PREMIUM_EMOJI_IDS.keys(), key=len, reverse=True):
        doc_id = PREMIUM_EMOJI_IDS[emoji]
        out = out.replace(emoji, f'<tg-emoji emoji-id="{doc_id}">{emoji}</tg-emoji>')
    return out


# ====================== CLIENT ======================
client = TelegramClient('nova_finder', API_ID, API_HASH)
client_instance = client


# ====================== MESSAGE HELPERS ======================
def build_entities(html_text, emoji_ids=None):
    text, entities = thtml.parse(html_text)
    if emoji_ids:
        idx, utf16_pos = 0, 0
        for ch in text:
            if ch == PE and idx < len(emoji_ids):
                entities.append(MessageEntityCustomEmoji(
                    offset=utf16_pos, length=1, document_id=emoji_ids[idx]))
                idx += 1
            utf16_pos += 2 if ord(ch) > 0xFFFF else 1
    return text, sorted(entities, key=lambda e: e.offset)


async def styled_reply(event, html_text, buttons=None, emoji_ids=None, file=None):
    try:
        text, entities = build_entities(html_text, emoji_ids)
        return await asyncio.wait_for(
            event.reply(text, formatting_entities=entities, buttons=buttons,
                        file=file, link_preview=False), timeout=15)
    except asyncio.TimeoutError:
        return None
    except Exception as e:
        log_system("REPLY", f"failed: {e}", "error")
        try:
            return await asyncio.wait_for(
                event.reply(html_text[:4000], parse_mode='html',
                            link_preview=False), timeout=10)
        except Exception:
            return None


async def styled_edit(msg, html_text, buttons=None, emoji_ids=None):
    if msg is None:
        return
    try:
        text, entities = build_entities(html_text, emoji_ids)
        await msg.edit(text, formatting_entities=entities,
                       buttons=buttons, link_preview=False)
        return
    except Exception as e:
        log_system("EDIT", f"entity edit failed: {e}", "warning")
    try:
        await msg.edit(html_text[:4000], buttons=buttons,
                       parse_mode='html', link_preview=False)
    except Exception as e:
        log_system("EDIT", f"html edit failed: {e}", "error")


async def send_entities(chat_id, html_text, buttons=None, file=None, **kwargs):
    try:
        text, ents = build_entities(html_text)
        return await client_instance.send_message(
            chat_id, text, formatting_entities=ents,
            buttons=buttons, link_preview=False, **kwargs)
    except Exception as e:
        log_system("SEND", f"send_entities failed: {e}", "error")
        return None


async def send_file_entities(chat_id, file, html_caption, buttons=None, **kwargs):
    try:
        text, ents = build_entities(html_caption)
        return await client_instance.send_file(
            chat_id, file, caption=text, formatting_entities=ents,
            buttons=buttons, **kwargs)
    except Exception as e:
        log_system("SEND_FILE", f"send_file_entities failed: {e}", "error")
        return None


async def edit_with_entities(event, html_text, buttons=None, emoji_ids=None):
    try:
        text, ents = build_entities(html_text, emoji_ids)
        await event.edit(text, formatting_entities=ents,
                         buttons=buttons, link_preview=False)
        return True
    except Exception as e:
        log_system("CB_EDIT", f"entity failed: {e}", "warning")
    try:
        await event.edit(html_text[:4000], buttons=buttons,
                         parse_mode='html', link_preview=False)
        return True
    except Exception as e:
        log_system("CB_EDIT", f"html failed: {e}", "error")
        return False


def pbtn(text, data=None, url=None):
    if url:
        return Button.url(text, url)
    if data:
        return Button.inline(text, data.encode() if isinstance(data, str) else data)
    return Button.inline(text, b"none")


# ====================== JSON STORAGE ======================
def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        log_system("FS", f"write {path} failed: {e}", "error")


# ====================== SOURCE CONFIG ======================
def get_source() -> str:
    d = _read_json(SOURCE_FILE, {})
    return d.get("url") or DEFAULT_SOURCE


def set_source(url: str):
    _write_json(SOURCE_FILE, {"url": url, "updated": datetime.now().isoformat()})


def get_check_api() -> str:
    d = _read_json(CHECK_API_FILE, {})
    return d.get("url") or CHECK_API_DEFAULT


def set_check_api(url: str):
    _write_json(CHECK_API_FILE, {"url": url, "updated": datetime.now().isoformat()})


# ====================== POOL STORAGE ======================
def load_pool(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return [ln.strip() for ln in f if ln.strip()]
    except Exception:
        return []


def save_pool(path, items):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            for s in items:
                f.write(s + "\n")
    except Exception as e:
        log_system("FS", f"save pool {path} failed: {e}", "error")


def append_pool(path, items):
    try:
        existing = set(load_pool(path))
        with open(path, 'a', encoding='utf-8') as f:
            for s in items:
                if s not in existing:
                    f.write(s + "\n")
                    existing.add(s)
    except Exception as e:
        log_system("FS", f"append pool {path} failed: {e}", "error")


# ====================== HTTP ======================
_GLOBAL_HTTP = None


async def get_http_session():
    global _GLOBAL_HTTP
    if _GLOBAL_HTTP is None or _GLOBAL_HTTP.closed:
        _GLOBAL_HTTP = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=90, connect=20),
            connector=aiohttp.TCPConnector(
                limit=200, limit_per_host=50,
                ttl_dns_cache=600, use_dns_cache=True,
                enable_cleanup_closed=True,
            ),
            headers={"User-Agent": "Mozilla/5.0 (compatible; NovaFinder/2.1)"},
        )
    return _GLOBAL_HTTP


# ====================== NORMALIZERS ======================
_BAD_HOSTS = {
    "shopify.com", "www.shopify.com", "shop.app", "www.shop.app",
    "google.com", "facebook.com", "instagram.com", "youtube.com",
    "cdn.shopify.com", "myshopify.com",
}


def norm_shopify(raw) -> str:
    """Return hostname (no scheme, no path) for any valid domain. Not just myshopify."""
    if not raw:
        return ""
    s = str(raw).strip().lower()
    s = re.sub(r'^https?://', '', s)
    s = s.rstrip('/').split('/')[0].split('?')[0]
    if s.startswith('www.'):
        s = s[4:]
    if not s or '.' not in s:
        return ""
    # basic hostname shape
    if not re.match(
        r'^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+$',
        s
    ):
        return ""
    if s in _BAD_HOSTS:
        return ""
    # must have a real TLD
    tld = s.rsplit('.', 1)[-1]
    if len(tld) < 2 or tld.isdigit():
        return ""
    return s


def full_url(host: str) -> str:
    """Return https://host for display/storage."""
    if not host:
        return ""
    return f"https://{host}"


# ====================== SOURCE FETCH ======================
def _extract_urls_from_json(obj, depth=0):
    """Walk JSON, yield every string that looks like a domain-bearing URL."""
    if depth > 8:
        return
    if isinstance(obj, str):
        s = obj.strip()
        if "." in s and (s.startswith(("http://", "https://")) or "." in s):
            yield s
        return
    if isinstance(obj, dict):
        # Prioritize common keys
        for k in ("url", "domain", "shop", "store", "site", "host",
                  "shopify_url", "storefront", "product_url"):
            v = obj.get(k)
            if isinstance(v, str):
                yield v
        for v in obj.values():
            yield from _extract_urls_from_json(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from _extract_urls_from_json(v, depth + 1)


async def fetch_from_source(keyword: str, count: int = 250,
                            min_price: int = 0, max_price: int = 8,
                            price_tier: str = "low",
                            condition: str = "new") -> list:
    """
    Hit the worker with the exact param shape it expects.
    Returns deduped list of normalized hostnames.
    """
    source = get_source().rstrip("/")

    # Worker caps at 250 per call; scale with count
    result_count = min(max(10, count), 250)

    params = {
        "keyword": keyword,
        "result": result_count,
        "min": min_price,
        "max": max_price,
        "price_tier": price_tier,
        "condition": condition,
    }

    session = await get_http_session()
    seen = set()
    out = []

    try:
        async with session.get(source, params=params,
                                timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                log_system("FETCH", f"status {r.status}", "warning")
                return []
            ctype = (r.headers.get("content-type") or "").lower()
            if "json" in ctype:
                try:
                    data = await r.json(content_type=None)
                except Exception as e:
                    log_system("FETCH", f"json parse: {e}", "warning")
                    return []
                for raw in _extract_urls_from_json(data):
                    host = norm_shopify(raw)
                    if host and host not in seen:
                        seen.add(host)
                        out.append(host)
            else:
                text = await r.text()
                for m in re.finditer(
                    r'https?://([a-z0-9][a-z0-9\-\.]*\.[a-z]{2,})',
                    text, re.IGNORECASE
                ):
                    host = norm_shopify(m.group(1))
                    if host and host not in seen:
                        seen.add(host)
                        out.append(host)
    except Exception as e:
        log_system("FETCH", f"{str(e)[:80]}", "warning")

    return out


async def fetch_many(keywords: list, count_per_kw: int = 250) -> list:
    """Run multiple keywords sequentially, merge deduped."""
    merged = []
    seen = set()
    for kw in keywords:
        try:
            got = await fetch_from_source(kw, count_per_kw)
            for h in got:
                if h not in seen:
                    seen.add(h)
                    merged.append(h)
            log_system("SWEEP", f"{kw} → {len(got)} new (total {len(merged)})")
        except Exception as e:
            log_system("SWEEP", f"{kw}: {e}", "warning")
        await asyncio.sleep(0.4)
    return merged


# ====================== ALIVE CHECK ======================
async def check_shopify_alive(site: str) -> dict:
    if not site:
        return {"site": site, "status": "dead", "msg": "empty"}
    base = get_check_api()
    if not site.startswith('http'):
        site = f'https://{site}'
    url = f"{base}?site={quote(site, safe='')}&cc={quote(TEST_CARD, safe='')}"
    session = await get_http_session()
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(
                total=CHECK_API_TIMEOUT, connect=15)) as r:
            if r.status != 200:
                return {"site": site, "status": "dead", "msg": f"HTTP_{r.status}"}
            try:
                rj = await r.json(content_type=None)
            except Exception:
                return {"site": site, "status": "dead", "msg": "bad json"}
    except Exception as e:
        return {"site": site, "status": "dead", "msg": str(e)[:60]}

    resp = str(rj.get('Response', rj.get('response', '')) or '')
    low = resp.lower()
    dead_markers = [
        "shop not found", "store not found", "site not found",
        "invalid site", "invalid store", "no such shop",
        "could not resolve", "dns error", "unavailable",
        "currently unavailable", "store closed", "shop closed",
        "password protected", "not shopify", "no products",
        "no valid products", "failed to detect product",
    ]
    if any(k in low for k in dead_markers):
        return {"site": site, "status": "dead", "msg": resp[:60]}
    return {"site": site, "status": "alive", "msg": resp[:60] or "reached"}


# ====================== STREAMED DISPLAY ======================
async def stream_results(event, uid, items, save=True):
    if not items:
        return await styled_reply(event, pe(
            f"❌ <b>{bs('No results found')}</b>\n"
            f"💡 {bs('Try another keyword or check')} <code>/source</code>"),
            emoji_ids=[PE])

    added = 0
    if save:
        existing = set(load_pool(SHOPIFY_POOL_FILE))
        new = [a for a in items if a not in existing]
        if new:
            append_pool(SHOPIFY_POOL_FILE, new)
            added = len(new)
        meta = _read_json(SHOPIFY_META_FILE, {})
        meta["last_run"] = datetime.now().isoformat()
        meta["total_runs"] = int(meta.get("total_runs", 0)) + 1
        meta["last_found"] = len(items)
        meta["last_added"] = added
        _write_json(SHOPIFY_META_FILE, meta)

    total = len(items)
    chunks = [items[i:i + RESULT_CHUNK] for i in range(0, total, RESULT_CHUNK)]

    await styled_reply(event, pe(
        f"✅ <b>{bs('Search Complete')}</b>\n"
        f"{SEP}\n"
        f"📊 {bs('Found')}: <code>{total}</code>\n"
        f"➕ {bs('New to pool')}: <code>{added}</code>\n"
        f"📁 {bs('Pool total')}: <code>{len(load_pool(SHOPIFY_POOL_FILE))}</code>\n"
        f"{SEP}\n"
        f"📥 {bs('Streaming below...')}"),
        emoji_ids=[PE, PE, PE, PE, PE, PE])

    for i, chunk in enumerate(chunks, 1):
        body = "\n".join(
            f"{j}. <code>{site}</code>"
            for j, site in enumerate(chunk, (i - 1) * RESULT_CHUNK + 1)
        )
        header = f"{PE} <b>{bs('Part')} {i}/{len(chunks)}</b>\n{SEP}\n"
        try:
            await send_entities(event.chat_id, header + body)
        except Exception:
            pass
        await asyncio.sleep(0.4)

    buttons = [
        [pbtn(bs("📥 Download pool"), data=f"dl:{uid}")],
        [pbtn(bs("🔙 Menu"), data="menu_main")],
    ]

    await styled_reply(event, pe(
        f"💎 <b>{bs('Done')}</b>\n"
        f"📁 {bs('Pool')}: <code>{len(load_pool(SHOPIFY_POOL_FILE))}</code>\n"
        f"💡 {bs('Download below')}"),
        buttons=buttons, emoji_ids=[PE, PE, PE])


# ====================== COMMANDS ======================
@client.on(events.NewMessage(pattern=r'^[/.]start$'))
async def cmd_start(event):
    uid = event.sender_id
    is_admin = uid in ADMIN_ID
    tier = "👑 Admin" if is_admin else "🆓 Free"
    text = pe(f"""{SEP}
    ✨ {bs('NOVA FINDER')} ✨
{SEP}
👤 {bs('User')}: <code>{uid}</code>
📊 {bs('Tier')}: {tier}
{SEP}
🔍 <b>{bs('Commands')}</b>
┣ <code>• /shsearch coffee 100</code>
┣ <code>• /shsearch 100</code>
┣ <code>• /shsweep 20</code>
┣ <code>• /shdeep seed.com</code>
{SEP}
📁 <b>{bs('Pool')}</b>
┣ <code>• /shsave</code> · <code>• /shstats</code>
┗ <code>• /shclear</code>
{SEP}
🔧 <b>{bs('Tools')}</b>
┣ <code>• /shcheck site.com</code>
┗ <code>• /source</code>
{SEP}
{DEV_LINE}""")

    buttons = [
        [pbtn(bs("🔍 Search"), data="menu_search")],
        [pbtn(bs("📊 Stats"), data="menu_stats"),
         pbtn(bs("❌ Close"), data="menu_close")],
    ]
    if is_admin:
        buttons.append([pbtn(bs("👑 Admin"), data="menu_admin")])
    await styled_reply(event, text, buttons=buttons,
                        emoji_ids=[PE, PE, PE, PE])


@client.on(events.CallbackQuery(data=b"menu_main"))
async def cb_main(event):
    await event.answer()
    uid = event.sender_id
    is_admin = uid in ADMIN_ID
    text = pe(f"""💎 <b>{bs('NOVA FINDER')}</b>
{SEP}
👤 <code>{uid}</code>
{SEP}
💡 {bs('Pick an option')}""")
    buttons = [
        [pbtn(bs("🔍 Search"), data="menu_search")],
        [pbtn(bs("📊 Stats"), data="menu_stats"),
         pbtn(bs("❌ Close"), data="menu_close")],
    ]
    if is_admin:
        buttons.append([pbtn(bs("👑 Admin"), data="menu_admin")])
    await edit_with_entities(event, text, buttons=buttons,
                              emoji_ids=[PE, PE])


@client.on(events.CallbackQuery(data=b"menu_close"))
async def cb_close(event):
    await event.answer()
    try:
        await event.delete()
    except Exception:
        pass


@client.on(events.CallbackQuery(data=b"menu_search"))
async def cb_menu_search(event):
    await event.answer()
    text = pe(f"""🔍 <b>{bs('Search Shopify')}</b>
{SEP}
📥 <code>• /shsearch coffee 100</code>
📥 <code>• /shsearch 100</code>
🌊 <code>• /shsweep 20</code>
🌱 <code>• /shdeep seed.com</code>
{SEP}
📁 <code>• /shsave</code> · <code>• /shstats</code>
🗑 <code>• /shclear</code>""")
    buttons = [[pbtn(bs("🔙 Back"), data="menu_main")]]
    await edit_with_entities(event, text, buttons=buttons,
                              emoji_ids=[PE, PE])


@client.on(events.CallbackQuery(data=b"menu_stats"))
async def cb_menu_stats(event):
    await event.answer()
    pool = load_pool(SHOPIFY_POOL_FILE)
    meta = _read_json(SHOPIFY_META_FILE, {})
    last = meta.get("last_run", "-")[:19] if meta.get("last_run") else "-"
    text = pe(f"""📊 <b>{bs('Pool Stats')}</b>
{SEP}
📁 {bs('Pool size')}: <code>{len(pool)}</code>
🔁 {bs('Runs')}: <code>{meta.get('total_runs', 0)}</code>
✅ {bs('Last found')}: <code>{meta.get('last_found', 0)}</code>
➕ {bs('Last added')}: <code>{meta.get('last_added', 0)}</code>
🕐 {bs('Last run')}: <code>{last}</code>
{SEP}
📡 <code>{get_source()[:60]}</code>""")
    buttons = [[pbtn(bs("🔙 Back"), data="menu_main")]]
    await edit_with_entities(event, text, buttons=buttons,
                              emoji_ids=[PE, PE, PE])


@client.on(events.CallbackQuery(data=b"menu_admin"))
async def cb_menu_admin(event):
    if event.sender_id not in ADMIN_ID:
        return await event.answer("Access denied", alert=True)
    await event.answer()
    text = pe(f"""👑 <b>{bs('Admin Panel')}</b>
{SEP}
📡 <b>{bs('Source')}</b>
└ <code>{get_source()[:70]}</code>
{SEP}
🔌 <b>{bs('Check API')}</b>
└ <code>{get_check_api()[:70]}</code>
{SEP}
⚙️ <code>• /setsource URL</code>
⚙️ <code>• /setcheckapi URL</code>
⚙️ <code>• /resetsource</code>
{SEP}
👑 <code>• /addadmin ID</code>
👑 <code>• /removeadmin ID</code>""")
    buttons = [[pbtn(bs("🔙 Back"), data="menu_main")]]
    await edit_with_entities(event, text, buttons=buttons,
                              emoji_ids=[PE, PE])


# ====================== SEARCH COMMANDS ======================
@client.on(events.NewMessage(pattern=r'^[/.]shsearch(?:\s+(.+))?$'))
async def cmd_shsearch(event):
    uid = event.sender_id
    arg = (event.pattern_match.group(1) or "").strip()

    count = 100
    keyword = ""
    if arg:
        parts = arg.split()
        nums = [p for p in parts if p.isdigit()]
        words = [p for p in parts if not p.isdigit()]
        if nums:
            count = max(10, min(int(nums[0]), MAX_PER_QUERY))
        if words:
            keyword = " ".join(words)
    if not keyword:
        keyword = random.choice(SEED_KEYWORDS)

    status = await styled_reply(event, pe(
        f"💎 <b>{bs('Searching Shopify')}</b>\n"
        f"🔑 <code>{keyword}</code> · 🎯 <code>{count}</code>"),
        emoji_ids=[PE, PE])

    try:
        results = await fetch_from_source(keyword, count)
    except Exception as e:
        return await styled_edit(status, pe(
            f"❌ <b>{bs('Error')}</b>: <code>{str(e)[:120]}</code>"),
            emoji_ids=[PE])

    try:
        await status.delete()
    except Exception:
        pass

    await stream_results(event, uid, results, save=True)


@client.on(events.NewMessage(pattern=r'^[/.]shsweep(?:\s+(\d+))?$'))
async def cmd_shsweep(event):
    """Multi-keyword sweep — pulls fresh sites across N seed keywords."""
    uid = event.sender_id
    m = event.pattern_match.group(1)
    kw_count = 10
    if m:
        try:
            kw_count = max(1, min(int(m), MAX_KEYWORDS_PER_RUN))
        except ValueError:
            kw_count = 10

    picks = random.sample(SEED_KEYWORDS, min(kw_count, len(SEED_KEYWORDS)))
    status = await styled_reply(event, pe(
        f"🌊 <b>{bs('Sweeping')}</b> <code>{len(picks)}</code> {bs('keywords')}...\n"
        f"{SEP}\n"
        f"<i>{', '.join(picks[:8])}{'…' if len(picks) > 8 else ''}</i>"),
        emoji_ids=[PE, PE])

    try:
        merged = await fetch_many(picks, count_per_kw=250)
    except Exception as e:
        return await styled_edit(status, pe(
            f"❌ <b>{bs('Error')}</b>: <code>{str(e)[:120]}</code>"),
            emoji_ids=[PE])

    try:
        await status.delete()
    except Exception:
        pass

    await stream_results(event, uid, merged, save=True)


@client.on(events.NewMessage(pattern=r'^[/.]shdeep\s+(.+)$'))
async def cmd_shdeep(event):
    uid = event.sender_id
    seed = event.pattern_match.group(1).decode().strip()
    seed_clean = norm_shopify(seed) or seed
    parts = seed_clean.split('.')
    keyword = re.sub(r'[^a-z0-9]', '', parts[0] if parts else "") or "shop"

    status = await styled_reply(event, pe(
        f"💎 <b>{bs('Expanding')}</b>\n🌱 <code>{seed_clean}</code>"),
        emoji_ids=[PE, PE])
    try:
        results = await fetch_from_source(keyword, 250)
    except Exception as e:
        return await styled_edit(status, pe(
            f"❌ <b>{bs('Error')}</b>: <code>{str(e)[:120]}</code>"),
            emoji_ids=[PE])
    try:
        await status.delete()
    except Exception:
        pass
    await stream_results(event, uid, results, save=True)


# ====================== POOL COMMANDS ======================
@client.on(events.NewMessage(pattern=r'^[/.]shsave$'))
async def cmd_shsave(event):
    uid = event.sender_id
    pool = load_pool(SHOPIFY_POOL_FILE)
    if not pool:
        return await styled_reply(event, pe(
            f"💎 <b>{bs('Pool empty')}</b>"), emoji_ids=[PE])
    fname = f"shopify_pool_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        async with aiofiles.open(fname, 'w', encoding='utf-8') as f:
            for s in pool:
                await f.write(s + "\n")
        await send_file_entities(uid, fname, pe(
            f"📁 <b>{bs('Shopify Pool')}</b> — <code>{len(pool)}</code>"),
            emoji_ids=[PE, PE])
        os.remove(fname)
    except Exception as e:
        await styled_reply(event, pe(f"❌ <code>{e}</code>"), emoji_ids=[PE])


@client.on(events.NewMessage(pattern=r'^[/.]shstats$'))
async def cmd_shstats(event):
    pool = load_pool(SHOPIFY_POOL_FILE)
    meta = _read_json(SHOPIFY_META_FILE, {})
    last = meta.get("last_run", "-")[:19] if meta.get("last_run") else "-"
    sample_lines = []
    for i, s in enumerate(pool[:10], 1):
        sample_lines.append(f"{i}. <code>{s}</code>")
    if len(pool) > 10:
        sample_lines.append(f"<i>… +{len(pool)-10} more</i>")
    sample = "\n".join(sample_lines) if sample_lines else "<i>empty</i>"
    text = pe(f"""📊 <b>{bs('Shopify Pool')}</b>
{SEP}
📁 {bs('Size')}: <code>{len(pool)}</code>
🔁 {bs('Runs')}: <code>{meta.get('total_runs', 0)}</code>
✅ {bs('Last found')}: <code>{meta.get('last_found', 0)}</code>
➕ {bs('Last added')}: <code>{meta.get('last_added', 0)}</code>
🕐 {bs('Last run')}: <code>{last}</code>
{SEP}
{bs('Sample')}:
{sample}""")
    await styled_reply(event, text, emoji_ids=[PE, PE, PE, PE, PE])


@client.on(events.NewMessage(pattern=r'^[/.]shclear$'))
async def cmd_shclear(event):
    uid = event.sender_id
    if uid not in ADMIN_ID:
        return await styled_reply(event, pe(f"⚠️ <b>{bs('Admin only')}</b>"),
                                   emoji_ids=[PE])
    n = len(load_pool(SHOPIFY_POOL_FILE))
    save_pool(SHOPIFY_POOL_FILE, [])
    await styled_reply(event, pe(
        f"✅ <b>{bs('Cleared')}</b> <code>{n}</code>"), emoji_ids=[PE])


# ====================== SINGLE CHECK ======================
@client.on(events.NewMessage(pattern=r'^[/.]shcheck\s+(.+)$'))
async def cmd_shcheck(event):
    site = event.pattern_match.group(1).decode().strip()
    site_clean = norm_shopify(site) or site
    status = await styled_reply(event, pe(
        f"💎 {bs('Checking')} <code>{site_clean}</code>..."), emoji_ids=[PE])
    res = await check_shopify_alive(site_clean)
    tag = "✅" if res["status"] == "alive" else "❌"
    await styled_edit(status, pe(
        f"{tag} <b>{bs(res['status'].upper())}</b>\n"
        f"{SEP}\n"
        f"🌐 <code>{site_clean}</code>\n"
        f"📝 <i>{(res.get('msg') or '')[:80]}</i>"), emoji_ids=[PE])


# ====================== DOWNLOAD CALLBACK ======================
@client.on(events.CallbackQuery(pattern=rb"^dl:(\d+)$"))
async def cb_download(event):
    owner = int(event.pattern_match.group(1).decode())
    if event.sender_id != owner:
        return await event.answer("Not yours!", alert=True)
    pool = load_pool(SHOPIFY_POOL_FILE)
    if not pool:
        return await event.answer("Pool empty", alert=True)
    fname = f"shopify_pool_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        async with aiofiles.open(fname, 'w', encoding='utf-8') as f:
            for s in pool:
                await f.write(s + "\n")
        await send_file_entities(event.sender_id, fname, pe(
            f"📁 <b>{bs('Shopify Pool')}</b> — <code>{len(pool)}</code>"),
            emoji_ids=[PE, PE])
        os.remove(fname)
    except Exception as e:
        log_system("DOWNLOAD", f"failed: {e}", "error")
    await event.answer("Sent!", alert=False)


# ====================== SOURCE ADMIN ======================
@client.on(events.NewMessage(pattern=r'^[/.]source$'))
async def cmd_source(event):
    await styled_reply(event, pe(
        f"📡 <b>{bs('Source')}</b>\n{SEP}\n"
        f"<code>{get_source()}</code>\n{SEP}\n"
        f"💡 {bs('Admin')}: <code>/setsource URL</code>"),
        emoji_ids=[PE, PE])


@client.on(events.NewMessage(pattern=r'^[/.]setsource\s+(.+)$'))
async def cmd_setsource(event):
    if event.sender_id not in ADMIN_ID:
        return
    url = event.pattern_match.group(1).decode().strip()
    if not url.startswith(("http://", "https://")):
        return await styled_reply(event, pe(
            f"❌ <b>{bs('URL must start with http')}</b>"), emoji_ids=[PE])
    set_source(url)
    await styled_reply(event, pe(
        f"✅ <b>{bs('Source updated')}</b>\n📡 <code>{url}</code>"),
        emoji_ids=[PE, PE])


@client.on(events.NewMessage(pattern=r'^[/.]setcheckapi\s+(.+)$'))
async def cmd_setcheckapi(event):
    if event.sender_id not in ADMIN_ID:
        return
    url = event.pattern_match.group(1).decode().strip()
    if not url.startswith(("http://", "https://")):
        return await styled_reply(event, pe(
            f"❌ <b>{bs('URL must start with http')}</b>"), emoji_ids=[PE])
    set_check_api(url)
    await styled_reply(event, pe(
        f"✅ <b>{bs('Check API updated')}</b>\n🔌 <code>{url}</code>"),
        emoji_ids=[PE, PE])


@client.on(events.NewMessage(pattern=r'^[/.]resetsource$'))
async def cmd_resetsource(event):
    if event.sender_id not in ADMIN_ID:
        return
    set_source(DEFAULT_SOURCE)
    await styled_reply(event, pe(
        f"✅ <b>{bs('Source reset')}</b>\n📡 <code>{DEFAULT_SOURCE}</code>"),
        emoji_ids=[PE])


# ====================== ADMIN MGMT ======================
@client.on(events.NewMessage(pattern=r'^[/.]addadmin\s+'))
async def cmd_addadmin(event):
    if event.sender_id not in ADMIN_ID:
        return
    parts = event.raw_text.split(maxsplit=1)
    if len(parts) < 2:
        return await styled_reply(event, pe(f"💎 <code>• /addadmin ID</code>"),
                                   emoji_ids=[PE])
    try:
        t = int(parts[1])
    except ValueError:
        return await styled_reply(event, pe(f"❌ <b>{bs('Invalid ID')}</b>"),
                                   emoji_ids=[PE])
    if t in ADMIN_ID:
        return await styled_reply(event, pe(f"💎 <b>{bs('Already admin')}</b>"),
                                   emoji_ids=[PE])
    ADMIN_ID.append(t)
    _save_admins()
    await styled_reply(event, pe(f"✅ <b>{bs('Admin added')}</b> <code>{t}</code>"),
                        emoji_ids=[PE])


@client.on(events.NewMessage(pattern=r'^[/.]removeadmin\s+'))
async def cmd_removeadmin(event):
    if event.sender_id not in ADMIN_ID:
        return
    parts = event.raw_text.split(maxsplit=1)
    if len(parts) < 2:
        return await styled_reply(event, pe(f"💎 <code>• /removeadmin ID</code>"),
                                   emoji_ids=[PE])
    try:
        t = int(parts[1])
    except ValueError:
        return await styled_reply(event, pe(f"❌ <b>{bs('Invalid ID')}</b>"),
                                   emoji_ids=[PE])
    if t not in ADMIN_ID:
        return await styled_reply(event, pe(f"💎 <b>{bs('Not an admin')}</b>"),
                                   emoji_ids=[PE])
    if len(ADMIN_ID) <= 1:
        return await styled_reply(event, pe(
            f"❌ <b>{bs('Cannot remove last admin')}</b>"), emoji_ids=[PE])
    ADMIN_ID.remove(t)
    _save_admins()
    await styled_reply(event, pe(f"✅ <b>{bs('Admin removed')}</b> <code>{t}</code>"),
                        emoji_ids=[PE])


# ====================== UTIL ======================
@client.on(events.NewMessage(pattern=r'^[/.]ping$'))
async def cmd_ping(event):
    t = time.time()
    m = await styled_reply(event, pe("🏓 ..."))
    if m:
        try:
            await m.edit(pe(f"🏓 <b>{bs('Pong')}</b> <code>{(time.time()-t)*1000:.1f}ms</code>"),
                         parse_mode='html')
        except Exception:
            pass


@client.on(events.NewMessage(pattern=r'^[/.]version$'))
async def cmd_version(event):
    if event.sender_id not in ADMIN_ID:
        return
    await styled_reply(event, pe(
        f"🤖 <b>{bs('NOVA Finder')}</b>\n{SEP}\n"
        f"📦 Version: <code>v2.1.0</code>\n"
        f"📡 Source: <code>{get_source()[:60]}</code>\n"
        f"🔌 Check API: <code>{get_check_api()[:60]}</code>"),
        emoji_ids=[PE, PE])


# ====================== MAIN ======================
async def main():
    global client_instance
    client_instance = client

    _load_admins()

    log_system("BOOT", "Starting NOVA Finder v2.1.0...")
    log_system("BOOT", f"Source: {get_source()}")
    log_system("BOOT", f"Check API: {get_check_api()}")
    log_system("BOOT", f"Admins: {ADMIN_ID}")

    if not BOT_TOKEN:
        log_system("BOOT", "BOT_TOKEN not set — aborting", "error")
        return

    if not os.path.exists(SHOPIFY_POOL_FILE):
        open(SHOPIFY_POOL_FILE, 'a').close()

    while True:
        try:
            log_system("BOOT", "Connecting...")
            await client.start(bot_token=BOT_TOKEN)
            log_system("BOOT", "✅ Finder online.")
            me = await client.get_me()
            log_system("BOOT", f"  bot=@{me.username}  id={me.id}")
            await client.run_until_disconnected()
        except FloodWaitError as e:
            log_system("FLOOD", f"Sleeping {e.seconds + 5}s", "warning")
            await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            log_system("CRASH", f"{type(e).__name__}: {e}", "error")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
