"""
BIN lookup — cached, multi-source.
"""
import aiohttp
import asyncio
import time

_CACHE = {}
_TTL = 86400


async def lookup(bin6: str) -> dict:
    bin6 = (bin6 or "")[:6]
    if len(bin6) < 6 or not bin6.isdigit():
        return _empty()
    c = _CACHE.get(bin6)
    if c and time.time() - c["_ts"] < _TTL:
        return c
    info = await _try_binlist(bin6)
    if info["brand"] == "-":
        info = await _try_antipublic(bin6)
    info["_ts"] = time.time()
    _CACHE[bin6] = info
    return info


async def lookup_many(bins: list) -> dict:
    res = await asyncio.gather(*[lookup(b) for b in bins], return_exceptions=True)
    return {b: (r if not isinstance(r, Exception) else _empty()) for b, r in zip(bins, res)}


def _empty():
    return {"brand": "-", "type": "-", "level": "-", "bank": "-", "country": "-", "flag": ""}


async def _try_binlist(bin6: str) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(f"https://lookup.binlist.net/{bin6}",
                             headers={"Accept-Version": "3"}) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    return {
                        "brand": (d.get("scheme") or "-").upper(),
                        "type": (d.get("type") or "-").upper(),
                        "level": (d.get("brand") or "-").upper(),
                        "bank": ((d.get("bank") or {}).get("name") or "-"),
                        "country": ((d.get("country") or {}).get("name") or "-"),
                        "flag": ((d.get("country") or {}).get("emoji") or ""),
                    }
    except Exception:
        pass
    return _empty()


async def _try_antipublic(bin6: str) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(f"https://bins.antipublic.cc/bins/{bin6}") as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    return {
                        "brand": (d.get("brand") or "-").upper(),
                        "type": (d.get("type") or "-").upper(),
                        "level": (d.get("level") or "-").upper(),
                        "bank": d.get("bank") or "-",
                        "country": d.get("country_name") or "-",
                        "flag": d.get("country_flag") or "",
                    }
    except Exception:
        pass
    return _empty()
