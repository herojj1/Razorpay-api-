# =============================================================================
# NOVA Finder — Shopify + Razorpay Site Search Bot (v1.1.0)
# =============================================================================
# Search-first. Shows candidate sites live. Test/save are optional.
# - /shsearch [keyword] [count]   → find Shopify stores
# - /rzsearch [keywords] [count]  → find Razorpay pages
# - /shdeep seed                  → expand from a seed domain
# - /shsave / /rzsave             → download pool
# - /shstats / /rzstats           → pool stats
# - /shclear / /rzclear           → wipe pool (admin)
# - /shcheck site                 → single Shopify test (optional)
# - /rzcheck url                  → single Razorpay test (optional)
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

# Pools
SHOPIFY_POOL_FILE = "shopify_pool.txt"
RZ_POOL_FILE      = "rz_pool.txt"
SHOPIFY_META_FILE = "shopify_pool_meta.json"
RZ_META_FILE      = "rz_pool_meta.json"

# API endpoints (optional — only used by /shcheck, /rzcheck)
API_DEFAULTS = {
    "shopify": os.getenv("FINDER_API_BASE_URL",
                         "https://web-production-e6929.up.railway.app/shopify"),
    "razorpay": os.getenv("FINDER_RZ_API_URL",
                          "https://rz.rcvan.indevs.in/rz"),
}
API_CONFIG_FILE = "finder_api.json"
API_TIMEOUT = 45
TEST_CARD = "5154623245618097|03|2032|156"

# Search tuning
STREAM_WORKERS = 40
RESULT_CHUNK = 30        # sites per message when streaming
MAX_RESULTS_PER_QUERY = 5000

# Shopify stem fallback
SHOPIFY_STEMS = [
    "coffee", "tea", "candle", "soap", "skincare", "beauty", "cosmetics",
    "fashion", "clothing", "apparel", "shoes", "jewelry", "accessories",
    "bags", "watches", "home", "kitchen", "bedding", "furniture", "decor",
    "art", "prints", "posters", "toys", "kids", "baby", "pets", "dog",
    "cat", "fitness", "sports", "outdoor", "camping", "garden", "plants",
    "tech", "gadgets", "electronics", "books", "stationery", "snacks",
    "food", "drinks", "wine", "beer", "supplements", "vitamins", "protein",
    "roasters", "boutique", "vintage", "modern", "organic", "natural",
    "handmade", "luxury", "minimalist", "sustainable", "eco", "wellness",
    "selfcare", "chocolate", "honey", "spice", "herbal", "ayurveda",
]

# Razorpay slug stems
RZ_STEMS = [
    "donate", "donation", "pay", "payment", "paynow", "checkout", "fees",
    "booking", "book", "order", "store", "shop", "buy", "buynow", "cart",
    "subscription", "subscribe", "register", "registration", "ticket",
    "tickets", "entry", "course", "schoolfees", "collegefees", "support",
    "supportus", "seva", "daan", "help", "sponsor", "fund", "temple",
    "church", "mandir", "ashram", "trust", "foundation", "ngo", "charity",
    "welfare", "trial", "starter", "basic", "premium", "annual", "monthly",
    "payfee", "payfees", "registernow", "joinnow", "join", "member",
    "membership", "fee", "feespayment", "onlinefee", "donateus",
]

# Shopify directory endpoints (public JSON)
SHOPIFY_DIRS = [
    "https://shop.app/api/search",
    "https://shop.app/api/storefronts",
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


# ====================== MESSAGE HELPERS ======================
client_instance = None


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
    except Exception:
        try:
            return await asyncio.wait_for(
                event.reply(html_text[:4000], parse_mode='html', link_preview=False),
                timeout=10)
        except Exception:
            return None


async def styled_edit(msg, html_text, buttons=None, emoji_ids=None):
    try:
        text, entities = build_entities(html_text, emoji_ids)
        await asyncio.wait_for(msg.edit(text, formatting_entities=entities,
                                        buttons=buttons, link_preview=False), timeout=8)
    except Exception:
        pass


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


# ====================== API CONFIG ======================
def _load_api_config():
    try:
        if os.path.exists(API_CONFIG_FILE):
            with open(API_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(API_DEFAULTS)
            merged.update({k: v for k, v in data.items() if k in API_DEFAULTS})
            return merged
    except Exception:
        pass
    return dict(API_DEFAULTS)


def _save_api_config(cfg):
    try:
        with open(API_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


API_CONFIG = _load_api_config()


def get_api(name):
    return API_CONFIG.get(name, API_DEFAULTS.get(name, ""))


def set_api(name, url):
    if name not in API_DEFAULTS:
        return False
    API_CONFIG[name] = url
    _save_api_config(API_CONFIG)
    return True


def reset_api():
    global API_CONFIG
    API_CONFIG = dict(API_DEFAULTS)
    _save_api_config(API_CONFIG)


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
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT, connect=15),
            connector=aiohttp.TCPConnector(
                limit=500, limit_per_host=200,
                ttl_dns_cache=600, use_dns_cache=True,
                enable_cleanup_closed=True,
            ),
        )
    return _GLOBAL_HTTP


# ====================== NORMALIZERS ======================
def norm_shopify(raw):
    if not raw:
        return ""
    s = str(raw).strip().lower()
    s = re.sub(r'^https?://', '', s)
    s = s.rstrip('/').split('/')[0].split('?')[0]
    if s.startswith('www.'):
        s = s[4:]
    if not s or '.' not in s:
        return ""
    if not re.match(
        r'^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+$',
        s
    ):
        return ""
    return s


def norm_rz(raw):
    if not raw:
        return ""
    s = str(raw).strip()
    if not s.startswith(('http://', 'https://')):
        s = 'https://' + s
    return s.rstrip('/')


# ====================== SHOPIFY SEARCH ======================
def _walk_urls(obj, depth=0):
    if depth > 6:
        return
    if isinstance(obj, str):
        if "myshopify.com" in obj or (obj.startswith("http") and "." in obj):
            yield obj
        return
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_urls(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_urls(v, depth + 1)


async def _sh_from_directory(keyword, count):
    session = await get_http_session()
    out, seen = [], set()
    kw = (keyword or random.choice(SHOPIFY_STEMS)).strip().lower()
    params = {"query": kw, "limit": min(count, 250)}
    for url in SHOPIFY_DIRS:
        if len(out) >= count:
            break
        try:
            async with session.get(
                url, params=params,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "Mozilla/5.0"},
            ) as r:
                if r.status != 200:
                    continue
                try:
                    data = await r.json(content_type=None)
                except Exception:
                    continue
                for u in _walk_urls(data):
                    d = norm_shopify(u)
                    if d and d not in seen:
                        seen.add(d)
                        out.append(d)
                        if len(out) >= count:
                            break
        except Exception:
            continue
    return out


def _sh_from_stems(keyword, count):
    out, seen = [], set()
    stems = list(SHOPIFY_STEMS)
    if keyword:
        k = re.sub(r'[^a-z0-9\-]', '', keyword.lower())
        if k:
            stems = [k] + [f"{k}{s}" for s in ("shop", "store", "co")] + stems
    suffixes = ["", "shop", "store", "co", "us", "uk", "app", "online", "official"]
    for stem in stems:
        if len(out) >= count:
            break
        stem = re.sub(r'[^a-z0-9\-]', '', stem.lower())
        if not stem:
            continue
        for suf in suffixes:
            if len(out) >= count:
                break
            d = f"{stem}{suf}.myshopify.com"
            if d not in seen:
                seen.add(d)
                out.append(d)
    return out


async def search_shopify(keyword="", count=200):
    out, seen = [], set()
    try:
        a = await _sh_from_directory(keyword, count)
        for d in a:
            if d not in seen:
                seen.add(d); out.append(d)
    except Exception as e:
        log_system("SH_SEARCH", f"directory failed: {e}", "warning")
    if len(out) < count:
        b = _sh_from_stems(keyword, count - len(out))
        for d in b:
            if d not in seen:
                seen.add(d); out.append(d)
    return out[:count]


async def search_shopify_deep(seed, count=300):
    seed_clean = norm_shopify(seed)
    if not seed_clean:
        return []
    parts = seed_clean.split('.')
    keyword = re.sub(r'[^a-z0-9]', '', parts[0] if parts else "")
    return await search_shopify(keyword, count)


# ====================== RAZORPAY SEARCH ======================
def search_razorpay(keywords, count=200):
    seen, out = set(), []
    hints = list(RZ_STEMS)
    for kw in keywords:
        k = re.sub(r'[^a-z0-9\-]', '', kw.lower())
        if k:
            hints = [k] + [f"{k}{s}" for s in ("now", "pay", "donate", "page")] + hints
    for slug in hints:
        if len(out) >= count:
            break
        u = f"https://pages.razorpay.com/{slug}"
        if u not in seen:
            seen.add(u); out.append(u)
    for city in ["delhi", "mumbai", "bangalore", "chennai", "kolkata",
                 "pune", "hyderabad", "ahmedabad", "jaipur", "lucknow"]:
        if len(out) >= count:
            break
        for prefix in ("iic", "pg", "razor", "pay"):
            u = f"https://pages.razorpay.com/{prefix}{city}"
            if u not in seen:
                seen.add(u); out.append(u)
            if len(out) >= count:
                break
    return out[:count]


# ====================== OPTIONAL SINGLE TESTERS ======================
async def test_shopify_site(site):
    if not site:
        return {"site": site, "status": "dead", "msg": "empty"}
    base = get_api("shopify")
    if not site.startswith('http'):
        site = f'https://{site}'
    url = f"{base}?site={quote(site, safe='')}&cc={quote(TEST_CARD, safe='')}"
    session = await get_http_session()
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(
                total=API_TIMEOUT, connect=15)) as r:
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


async def test_rz_site(site):
    if not site:
        return {"site": site, "status": "dead", "msg": "empty"}
    base = get_api("razorpay")
    url = f"{base}?cc={quote(TEST_CARD, safe='')}"
    session = await get_http_session()
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(
                total=API_TIMEOUT, connect=15)) as r:
            if r.status != 200:
                return {"site": site, "status": "dead", "msg": f"HTTP_{r.status}"}
            try:
                rj = await r.json(content_type=None)
            except Exception:
                return {"site": site, "status": "dead", "msg": "bad json"}
    except Exception as e:
        return {"site": site, "status": "dead", "msg": str(e)[:60]}

    resp = str(rj.get('response', rj.get('Response', '')) or '')
    low = resp.lower()
    dead_markers = ["payment id not found", "invalid", "not found",
                    "does not exist", "no such", "expired", "inactive"]
    if not resp or any(k in low for k in dead_markers):
        return {"site": site, "status": "dead", "msg": resp[:60] or "empty"}
    return {"site": site, "status": "alive", "msg": resp[:60] or "reached"}


# ====================== STREAMED DISPLAY ======================
async def stream_results(event, uid, items, mode, save=True):
    """
    Stream results to the chat in chunks.
    Mode: 'shopify' | 'razorpay'
    """
    if not items:
        return await styled_reply(event, pe(
            f"❌ <b>{bs('No results found')}</b>"), emoji_ids=[PE])

    pool_file = SHOPIFY_POOL_FILE if mode == "shopify" else RZ_POOL_FILE
    meta_file = SHOPIFY_META_FILE if mode == "shopify" else RZ_META_FILE
    label = "Shopify" if mode == "shopify" else "Razorpay"

    added = 0
    if save:
        existing = set(load_pool(pool_file))
        new = [a for a in items if a not in existing]
        if new:
            append_pool(pool_file, new)
            added = len(new)
        meta = _read_json(meta_file, {})
        meta["last_run"] = datetime.now().isoformat()
        meta["total_runs"] = int(meta.get("total_runs", 0)) + 1
        meta["last_found"] = len(items)
        meta["last_added"] = added
        _write_json(meta_file, meta)

    total = len(items)
    chunks = [items[i:i + RESULT_CHUNK] for i in range(0, total, RESULT_CHUNK)]

    # Header
    await styled_reply(event, pe(
        f"✅ <b>{bs(label)} Search Complete</b>\n"
        f"{SEP}\n"
        f"📊 {bs('Found')}: <code>{total}</code>\n"
        f"➕ {bs('New to pool')}: <code>{added}</code>\n"
        f"📁 {bs('Pool total')}: <code>{len(load_pool(pool_file))}</code>\n"
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
        await asyncio.sleep(0.5)

    # Footer
    buttons = []
    if mode == "shopify":
        buttons.append([pbtn(bs("📥 Download pool"), data=f"download_shopify:{uid}")])
    else:
        buttons.append([pbtn(bs("📥 Download pool"), data=f"download_razorpay:{uid}")])
    buttons.append([pbtn(bs("🔙 Menu"), data="main_menu")])

    await styled_reply(event, pe(
        f"💎 <b>{bs('Done')}</b>\n"
        f"📁 {bs('Pool')}: <code>{len(load_pool(pool_file))}</code>\n"
        f"💡 {bs('Download with the button below')}"),
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
🔍 <b>{bs('Shopify Search')}</b>
┣ <code>• /shsearch coffee 200</code>
┣ <code>• /shsearch 500</code>
┗ <code>• /shdeep seed.myshopify.com</code>
{SEP}
💳 <b>{bs('Razorpay Search')}</b>
┣ <code>• /rzsearch donate,pay 300</code>
┗ <code>• /rzsearch 500</code>
{SEP}
📁 <b>{bs('Pool')}</b>
┣ <code>• /shsave</code> · <code>• /shstats</code>
┗ <code>• /rzsave</code> · <code>• /rzstats</code>
{SEP}
🔧 <b>{bs('Optional Checks')}</b>
┣ <code>• /shcheck site.com</code>
┗ <code>• /rzcheck URL</code>
{SEP}
{DEV_LINE}""")

    buttons = [
        [pbtn(bs("🔍 Shopify"), data="menu_shopify"),
         pbtn(bs("💳 Razorpay"), data="menu_razorpay")],
        [pbtn(bs("📊 Stats"), data="menu_stats"),
         pbtn(bs("❌ Close"), data="close_menu")],
    ]
    if is_admin:
        buttons.append([pbtn(bs("👑 Admin"), data="menu_admin")])
    await styled_reply(event, text, buttons=buttons,
                        emoji_ids=[PE, PE, PE, PE])


@client.on(events.CallbackQuery(data=b"main_menu"))
async def cb_main(event):
    await event.answer()
    uid = event.sender_id
    is_admin = uid in ADMIN_ID
    text = pe(f"""💎 <b>{bs('NOVA FINDER')}</b>
{SEP}
👤 <code>{uid}</code>
{SEP}
💡 {bs('Pick a search mode')}""")
    buttons = [
        [pbtn(bs("🔍 Shopify"), data="menu_shopify"),
         pbtn(bs("💳 Razorpay"), data="menu_razorpay")],
        [pbtn(bs("📊 Stats"), data="menu_stats"),
         pbtn(bs("❌ Close"), data="close_menu")],
    ]
    if is_admin:
        buttons.append([pbtn(bs("👑 Admin"), data="menu_admin")])
    try:
        await event.edit(*build_entities(text), buttons=buttons,
                         link_preview=False)
    except Exception:
        pass


@client.on(events.CallbackQuery(data=b"close_menu"))
async def cb_close(event):
    await event.answer()
    try:
        await event.delete()
    except Exception:
        pass


@client.on(events.CallbackQuery(data=b"menu_shopify"))
async def cb_menu_shopify(event):
    await event.answer()
    text = pe(f"""🔍 <b>{bs('Shopify Search')}</b>
{SEP}
📥 <code>• /shsearch coffee 200</code>
📥 <code>• /shsearch 500</code>
🌱 <code>• /shdeep seed.myshopify.com</code>
{SEP}
📁 <code>• /shsave</code> · <code>• /shstats</code>
🗑 <code>• /shclear</code>
{SEP}
💡 {bs('Results stream to chat + auto-save to pool')}""")
    buttons = [[pbtn(bs("🔙 Back"), data="main_menu")]]
    try:
        await event.edit(*build_entities(text), buttons=buttons,
                         link_preview=False)
    except Exception:
        pass


@client.on(events.CallbackQuery(data=b"menu_razorpay"))
async def cb_menu_razorpay(event):
    await event.answer()
    text = pe(f"""💳 <b>{bs('Razorpay Search')}</b>
{SEP}
📥 <code>• /rzsearch donate,pay 300</code>
📥 <code>• /rzsearch 500</code>
{SEP}
📁 <code>• /rzsave</code> · <code>• /rzstats</code>
🗑 <code>• /rzclear</code>
{SEP}
💡 {bs('Results stream to chat + auto-save to pool')}""")
    buttons = [[pbtn(bs("🔙 Back"), data="main_menu")]]
    try:
        await event.edit(*build_entities(text), buttons=buttons,
                         link_preview=False)
    except Exception:
        pass


@client.on(events.CallbackQuery(data=b"menu_stats"))
async def cb_menu_stats(event):
    await event.answer()
    sh_pool = load_pool(SHOPIFY_POOL_FILE)
    rz_pool = load_pool(RZ_POOL_FILE)
    sh_meta = _read_json(SHOPIFY_META_FILE, {})
    rz_meta = _read_json(RZ_META_FILE, {})
    sh_last = sh_meta.get("last_run", "-")[:19] if sh_meta.get("last_run") else "-"
    rz_last = rz_meta.get("last_run", "-")[:19] if rz_meta.get("last_run") else "-"
    text = pe(f"""📊 <b>{bs('Pool Stats')}</b>
{SEP}
🔍 <b>Shopify</b>
┣ {bs('Pool size')}: <code>{len(sh_pool)}</code>
┣ {bs('Runs')}: <code>{sh_meta.get('total_runs', 0)}</code>
┗ {bs('Last run')}: <code>{sh_last}</code>
{SEP}
💳 <b>Razorpay</b>
┣ {bs('Pool size')}: <code>{len(rz_pool)}</code>
┣ {bs('Runs')}: <code>{rz_meta.get('total_runs', 0)}</code>
┗ {bs('Last run')}: <code>{rz_last}</code>
{SEP}
{DEV_LINE}""")
    buttons = [[pbtn(bs("🔙 Back"), data="main_menu")]]
    try:
        await event.edit(*build_entities(text), buttons=buttons,
                         link_preview=False)
    except Exception:
        pass


@client.on(events.CallbackQuery(data=b"menu_admin"))
async def cb_menu_admin(event):
    if event.sender_id not in ADMIN_ID:
        return await event.answer("Access denied", alert=True)
    await event.answer()
    text = pe(f"""👑 <b>{bs('Admin Panel')}</b>
{SEP}
🔌 <b>{bs('API Endpoints')}</b>
┣ 🛒 <code>{get_api('shopify')[:60]}</code>
┗ 💳 <code>{get_api('razorpay')[:60]}</code>
{SEP}
⚙️ <code>• /setapi shopify URL</code>
⚙️ <code>• /setapi razorpay URL</code>
⚙️ <code>• /resetapi</code>
{SEP}
👑 <code>• /addadmin ID</code>
👑 <code>• /removeadmin ID</code>""")
    buttons = [[pbtn(bs("🔙 Back"), data="main_menu")]]
    try:
        await event.edit(*build_entities(text), buttons=buttons,
                         link_preview=False)
    except Exception:
        pass


# ====================== SEARCH COMMANDS ======================
@client.on(events.NewMessage(pattern=r'^[/.]shsearch(?:\s+(.+))?$'))
async def cmd_shsearch(event):
    uid = event.sender_id
    arg = (event.pattern_match.group(1) or "").strip()

    # Flexible parse: "coffee 200" or "200 coffee" or just "coffee" or empty
    count = 200
    keyword = ""
    if arg:
        parts = arg.split()
        nums = [p for p in parts if p.isdigit()]
        words = [p for p in parts if not p.isdigit()]
        if nums:
            count = max(10, min(int(nums[0]), MAX_RESULTS_PER_QUERY))
        if words:
            keyword = " ".join(words)

    status = await styled_reply(event, pe(
        f"💎 <b>{bs('Searching Shopify')}</b>\n"
        f"🔑 <code>{keyword or 'auto'}</code> · 🎯 <code>{count}</code>"),
        emoji_ids=[PE, PE])

    try:
        results = await search_shopify(keyword, count)
    except Exception as e:
        return await styled_edit(status, pe(
            f"❌ <b>{bs('Search error')}</b>: <code>{e}</code>"), emoji_ids=[PE])

    try:
        await status.delete()
    except Exception:
        pass

    await stream_results(event, uid, results, "shopify", save=True)


@client.on(events.NewMessage(pattern=r'^[/.]rzsearch(?:\s+(.+))?$'))
async def cmd_rzsearch(event):
    uid = event.sender_id
    arg = (event.pattern_match.group(1) or "").strip()

    count = 200
    keywords = []
    if arg:
        parts = arg.split()
        nums = [p for p in parts if p.isdigit()]
        words = [p for p in parts if not p.isdigit()]
        if nums:
            count = max(10, min(int(nums[0]), MAX_RESULTS_PER_QUERY))
        if words:
            keywords = [w.strip() for w in " ".join(words).split(",") if w.strip()]

    status = await styled_reply(event, pe(
        f"💎 <b>{bs('Searching Razorpay')}</b>\n"
        f"🔑 <code>{','.join(keywords) if keywords else 'auto'}</code> · 🎯 <code>{count}</code>"),
        emoji_ids=[PE, PE])

    try:
        results = search_razorpay(keywords, count)
    except Exception as e:
        return await styled_edit(status, pe(
            f"❌ <b>{bs('Search error')}</b>: <code>{e}</code>"), emoji_ids=[PE])

    try:
        await status.delete()
    except Exception:
        pass

    await stream_results(event, uid, results, "razorpay", save=True)


@client.on(events.NewMessage(pattern=r'^[/.]shdeep\s+(.+)$'))
async def cmd_shdeep(event):
    uid = event.sender_id
    seed = event.pattern_match.group(1).decode().strip()
    status = await styled_reply(event, pe(
        f"💎 <b>{bs('Expanding')}</b>\n🌱 <code>{seed}</code>"),
        emoji_ids=[PE, PE])
    try:
        results = await search_shopify_deep(seed, 300)
    except Exception as e:
        return await styled_edit(status, pe(
            f"❌ <b>{bs('Error')}</b>: <code>{e}</code>"), emoji_ids=[PE])
    try:
        await status.delete()
    except Exception:
        pass
    await stream_results(event, uid, results, "shopify", save=True)


# ====================== POOL COMMANDS ======================
@client.on(events.NewMessage(pattern=r'^[/.]shsave$'))
async def cmd_shsave(event):
    return await _do_save(event, "shopify")


@client.on(events.NewMessage(pattern=r'^[/.]rzsave$'))
async def cmd_rzsave(event):
    return await _do_save(event, "razorpay")


async def _do_save(event, mode):
    uid = event.sender_id
    path = SHOPIFY_POOL_FILE if mode == "shopify" else RZ_POOL_FILE
    pool = load_pool(path)
    if not pool:
        return await styled_reply(event, pe(
            f"💎 <b>{bs('Pool empty')}</b>"), emoji_ids=[PE])
    fname = f"{mode}_pool_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        async with aiofiles.open(fname, 'w', encoding='utf-8') as f:
            for s in pool:
                await f.write(s + "\n")
        await send_file_entities(uid, fname, pe(
            f"📁 <b>{bs(mode.title())} Pool</b> — <code>{len(pool)}</code>"),
            emoji_ids=[PE, PE])
        os.remove(fname)
    except Exception as e:
        await styled_reply(event, pe(f"❌ <code>{e}</code>"), emoji_ids=[PE])


@client.on(events.NewMessage(pattern=r'^[/.]shstats$'))
async def cmd_shstats(event):
    return await _do_stats(event, "shopify")


@client.on(events.NewMessage(pattern=r'^[/.]rzstats$'))
async def cmd_rzstats(event):
    return await _do_stats(event, "razorpay")


async def _do_stats(event, mode):
    path = SHOPIFY_POOL_FILE if mode == "shopify" else RZ_POOL_FILE
    meta_path = SHOPIFY_META_FILE if mode == "shopify" else RZ_META_FILE
    pool = load_pool(path)
    meta = _read_json(meta_path, {})
    last = meta.get("last_run", "-")[:19] if meta.get("last_run") else "-"
    sample_lines = []
    for i, s in enumerate(pool[:10], 1):
        sample_lines.append(f"{i}. <code>{s}</code>")
    if len(pool) > 10:
        sample_lines.append(f"<i>… +{len(pool)-10} more</i>")
    sample = "\n".join(sample_lines) if sample_lines else "<i>empty</i>"
    label = "Shopify" if mode == "shopify" else "Razorpay"
    text = pe(f"""📊 <b>{bs(label)} Pool</b>
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
    return await _do_clear(event, "shopify")


@client.on(events.NewMessage(pattern=r'^[/.]rzclear$'))
async def cmd_rzclear(event):
    return await _do_clear(event, "razorpay")


async def _do_clear(event, mode):
    uid = event.sender_id
    if uid not in ADMIN_ID:
        return await styled_reply(event, pe(f"⚠️ <b>{bs('Admin only')}</b>"),
                                   emoji_ids=[PE])
    path = SHOPIFY_POOL_FILE if mode == "shopify" else RZ_POOL_FILE
    n = len(load_pool(path))
    save_pool(path, [])
    await styled_reply(event, pe(
        f"✅ <b>{bs('Cleared')}</b> <code>{n}</code>"), emoji_ids=[PE])


# ====================== OPTIONAL SINGLE CHECK ======================
@client.on(events.NewMessage(pattern=r'^[/.]shcheck\s+(.+)$'))
async def cmd_shcheck(event):
    uid = event.sender_id
    site = event.pattern_match.group(1).decode().strip()
    site_clean = norm_shopify(site) or site
    status = await styled_reply(event, pe(
        f"💎 {bs('Checking')} <code>{site_clean}</code>..."), emoji_ids=[PE])
    res = await test_shopify_site(site_clean)
    tag = "✅" if res["status"] == "alive" else "❌"
    await styled_edit(status, pe(
        f"{tag} <b>{bs(res['status'].upper())}</b>\n"
        f"{SEP}\n"
        f"🌐 <code>{site_clean}</code>\n"
        f"📝 <i>{(res.get('msg') or '')[:80]}</i>"), emoji_ids=[PE])


@client.on(events.NewMessage(pattern=r'^[/.]rzcheck\s+(.+)$'))
async def cmd_rzcheck(event):
    uid = event.sender_id
    site = event.pattern_match.group(1).decode().strip()
    site_clean = norm_rz(site)
    status = await styled_reply(event, pe(
        f"💎 {bs('Checking')} <code>{site_clean}</code>..."), emoji_ids=[PE])
    res = await test_rz_site(site_clean)
    tag = "✅" if res["status"] == "alive" else "❌"
    await styled_edit(status, pe(
        f"{tag} <b>{bs(res['status'].upper())}</b>\n"
        f"{SEP}\n"
        f"🌐 <code>{site_clean}</code>\n"
        f"📝 <i>{(res.get('msg') or '')[:80]}</i>"), emoji_ids=[PE])


# ====================== DOWNLOAD CALLBACK ======================
@client.on(events.CallbackQuery(pattern=rb"^download_(shopify|razorpay):(\d+)$"))
async def cb_download(event):
    mode = event.pattern_match.group(1).decode()
    owner = int(event.pattern_match.group(2).decode())
    if event.sender_id != owner:
        return await event.answer("Not yours!", alert=True)
    path = SHOPIFY_POOL_FILE if mode == "shopify" else RZ_POOL_FILE
    pool = load_pool(path)
    if not pool:
        return await event.answer("Pool empty", alert=True)
    fname = f"{mode}_pool_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        async with aiofiles.open(fname, 'w', encoding='utf-8') as f:
            for s in pool:
                await f.write(s + "\n")
        await send_file_entities(event.sender_id, fname, pe(
            f"📁 <b>{bs(mode.title())} Pool</b> — <code>{len(pool)}</code>"),
            emoji_ids=[PE, PE])
        os.remove(fname)
    except Exception as e:
        log_system("DOWNLOAD", f"failed: {e}", "error")
    await event.answer("Sent!", alert=False)


# ====================== API ADMIN ======================
@client.on(events.NewMessage(pattern=r'^[/.]setapi\s+'))
async def cmd_setapi(event):
    if event.sender_id not in ADMIN_ID:
        return
    parts = event.raw_text.split(maxsplit=2)
    if len(parts) < 3:
        return await styled_reply(event, pe(
            f"💎 <code>• /setapi shopify https://...</code>\n"
            f"<code>• /setapi razorpay https://...</code>"), emoji_ids=[PE])
    target = parts[1].strip().lower()
    url = parts[2].strip()
    if target not in ("shopify", "razorpay"):
        return await styled_reply(event, pe(
            f"❌ <b>{bs('Unknown target')}</b>: <code>{target}</code>"),
            emoji_ids=[PE])
    if not url.startswith(("http://", "https://")):
        return await styled_reply(event, pe(
            f"❌ <b>{bs('URL must start with http')}</b>"), emoji_ids=[PE])
    set_api(target, url)
    await styled_reply(event, pe(
        f"✅ <b>{bs('API updated')}</b>\n"
        f"🔌 <b>{bs(target.title())}</b>: <code>{url}</code>"),
        emoji_ids=[PE, PE])


@client.on(events.NewMessage(pattern=r'^[/.]resetapi$'))
async def cmd_resetapi(event):
    if event.sender_id not in ADMIN_ID:
        return
    reset_api()
    await styled_reply(event, pe(
        f"✅ <b>{bs('API reset')}</b>\n"
        f"🛒 <code>{get_api('shopify')}</code>\n"
        f"💳 <code>{get_api('razorpay')}</code>"),
        emoji_ids=[PE])


@client.on(events.NewMessage(pattern=r'^[/.]api$'))
async def cmd_api(event):
    if event.sender_id not in ADMIN_ID:
        return
    await styled_reply(event, pe(
        f"🔌 <b>{bs('API Endpoints')}</b>\n{SEP}\n"
        f"🛒 Shopify: <code>{get_api('shopify')}</code>\n"
        f"💳 Razorpay: <code>{get_api('razorpay')}</code>\n{SEP}\n"
        f"💡 <code>• /setapi shopify URL</code>\n"
        f"<code>• /setapi razorpay URL</code>\n"
        f"<code>• /resetapi</code>"),
        emoji_ids=[PE, PE])


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
        f"📦 Version: <code>v1.1.0</code>\n"
        f"🛒 Shopify API: <code>{get_api('shopify')[:60]}</code>\n"
        f"💳 Razorpay API: <code>{get_api('razorpay')[:60]}</code>\n"
        f"⚙️ Stream workers: <code>{STREAM_WORKERS}</code>"),
        emoji_ids=[PE, PE])


# ====================== MAIN ======================
async def main():
    global client_instance
    client_instance = client

    _load_admins()

    log_system("BOOT", "Starting NOVA Finder v1.1.0 (search-first)...")
    log_system("BOOT", f"Shopify API: {get_api('shopify')}")
    log_system("BOOT", f"Razorpay API: {get_api('razorpay')}")
    log_system("BOOT", f"Admins: {ADMIN_ID}")

    if not BOT_TOKEN:
        log_system("BOOT", "BOT_TOKEN not set — aborting", "error")
        return

    for f in (SHOPIFY_POOL_FILE, RZ_POOL_FILE):
        if not os.path.exists(f):
            open(f, 'a').close()

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
