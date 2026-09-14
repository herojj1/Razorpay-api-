"""
CardCheckout API — Server Entry Point (v2.0.2)
==============================================
FastAPI server exposing the Shopify checkout engine as an HTTP API.

Change log v2.0.2 (from v2.0.1):
    - Added Status field to CheckResponse (bot.py compatibility)
    - _build_response now populates both Response and Status
    - Lowered default CHECKER_THREADS from 200 to 60
    - Added INFO-level log line per hit

Endpoints
---------
GET  /health
    Returns service status and configuration.

GET  /check?card=NUM|MM|YYYY|CVV&url=SHOP_URL&proxy=http://user:pass@host:port[&low=true]
    Check a card via query parameters.

POST /check  (JSON body)
    Check a card via JSON body.

Environment variables
---------------------
CHECKER_THREADS  — thread-pool size (default 60)
CHECKER_RETRIES  — auto-retry count on retryable errors (default 1)
PORT             — listen port (default 8000)
"""

import os
import asyncio
import concurrent.futures
import functools
import logging
import time
from typing import Optional, Tuple

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from checkout_engine import (
    run_checkout_for_card,
    normalize_proxy,
    parse_card_entry,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cardcheckout.api")

THREAD_WORKERS = int(os.environ.get("CHECKER_THREADS", "60"))
MAX_RETRIES    = int(os.environ.get("CHECKER_RETRIES", "1"))

import threading as _threading

_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=THREAD_WORKERS,
    thread_name_prefix="chk",
)

_active_checks      = 0
_active_checks_lock = _threading.Lock()


def _inc_active():
    global _active_checks
    with _active_checks_lock:
        _active_checks += 1


def _dec_active():
    global _active_checks
    with _active_checks_lock:
        _active_checks -= 1


app = FastAPI(
    title="CardCheckout API",
    version="2.0.2",
    description="Shopify card-check API.",
    docs_url=None,
    redoc_url=None,
)


_DOCS_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CardCheckout API</title>
<link rel="stylesheet" href="https://unpkg.com/@phosphor-icons/web@2.1.1/src/regular/style.css"/>
<style>
body{font:15px system-ui;background:#0b0b14;color:#e6e6ef;padding:40px;line-height:1.7;max-width:900px;margin:auto}
h1{color:#a78bfa}code{background:#1a1a2a;padding:2px 6px;border-radius:4px;font-size:13px}
.card{background:#12121f;border:1px solid #23233a;border-radius:10px;padding:20px;margin:14px 0}
pre{background:#0a0a14;padding:14px;border-radius:8px;overflow-x:auto;font-size:12px;color:#c4b5fd}
.ok{color:#34d399}.warn{color:#fbbf24}</style>
</head><body>
<h1>CardCheckout API v2.0.2</h1>
<p>Returns <span class=ok>CHARGED</span> only when Shopify confirms a <b>real order</b>.</p>
<div class=card><b>GET /health</b><pre>curl /health</pre></div>
<div class=card><b>GET /check</b><pre>curl "/check?url=shop.com&card=NUM|MM|YYYY|CVV&proxy=USER:PASS@HOST:PORT"</pre></div>
<div class=card><b>POST /check</b><pre>curl -X POST /check -H "Content-Type: application/json" -d '{"card":"...","shop_url":"...","proxy":"...","low":true}'</pre></div>
</body></html>
"""


class CheckRequest(BaseModel):
    card:     Optional[str]  = None
    shop_url: Optional[str]  = None
    proxy:    Optional[str]  = None
    low:      bool           = True


class CheckResponse(BaseModel):
    Response:    str  = "ERROR"
    Status:      str  = ""
    CC:          str  = ""
    Price:       str  = ""
    Gate:        str  = "Shopify"
    Site:        str  = ""
    Charged:     str  = "False"
    status_code: str  = ""
    error:       str  = ""
    retryable:   bool = False
    receipt_url: str  = ""


def _validate_proxy(raw: str) -> Tuple[Optional[str], Optional[CheckResponse]]:
    if not raw or not raw.strip():
        return None, CheckResponse(
            Response="ERROR", Status="ERROR", status_code="PROXY_REQUIRED",
            error="proxy is required — e.g. http://user:pass@1.2.3.4:8080",
            retryable=False)
    try:
        return normalize_proxy(raw), None
    except Exception as exc:
        return None, CheckResponse(
            Response="ERROR", Status="ERROR", status_code="PROXY_INVALID",
            error=f"Invalid proxy format: {exc}", retryable=False)


def _validate_card(raw: str) -> Tuple[Optional[str], Optional[CheckResponse]]:
    import datetime as _dt
    if not raw or not raw.strip():
        return None, CheckResponse(
            Response="ERROR", Status="ERROR", status_code="CARD_REQUIRED",
            error="card is required — format: number|mm|yyyy|cvv",
            retryable=False)
    try:
        _num, _month, _year, _cvv = parse_card_entry(raw)
    except Exception as exc:
        return None, CheckResponse(
            Response="ERROR", Status="ERROR", status_code="CARD_INVALID",
            error=f"invalid card format: {exc}", retryable=False)
    now = _dt.datetime.utcnow()
    if _year < now.year or (_year == now.year and _month < now.month):
        return None, CheckResponse(
            Response="ERROR", Status="ERROR", status_code="CARD_EXPIRED",
            error=f"card expired: {_month:02d}/{_year}", retryable=False)
    return raw.strip(), None


def _validate_url(raw: str) -> Tuple[Optional[str], Optional[CheckResponse]]:
    import urllib.parse as _up
    if not raw or not raw.strip():
        return None, CheckResponse(
            Response="ERROR", Status="ERROR", status_code="URL_REQUIRED",
            error="shop url is required — e.g. https://store.myshopify.com",
            retryable=False)
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = _up.urlparse(url)
        hostname = parsed.hostname or ""
        if not hostname or "." not in hostname or " " in hostname:
            raise ValueError(hostname)
    except Exception:
        return None, CheckResponse(
            Response="ERROR", Status="ERROR", status_code="URL_INVALID",
            error=f"invalid shop url: {raw!r}", retryable=False)
    return url, None


def _build_response(res, shop_url: str = "") -> CheckResponse:
    status_name = res.status.name
    return CheckResponse(
        Response    = status_name,
        Status      = status_name,
        CC          = res.card or "",
        Price       = res.amount or "",
        Gate        = "Shopify",
        Site        = shop_url or res.shop_url or "",
        Charged     = "True" if status_name == "CHARGED" else "False",
        status_code = res.status_code or "",
        error       = str(res.error) if res.error else "",
        retryable   = res.retryable,
        receipt_url = res.receipt_url or "",
    )


async def _run_check(shop_url: str, card: str, proxy_url: str, low: bool) -> CheckResponse:
    loop     = asyncio.get_event_loop()
    attempts = 1 + MAX_RETRIES
    last: Optional[CheckResponse] = None

    for attempt in range(1, attempts + 1):
        t0 = time.perf_counter()
        _inc_active()
        try:
            fn  = functools.partial(run_checkout_for_card, shop_url, card, proxy_url, low)
            res = await loop.run_in_executor(_pool, fn)
        except Exception as exc:
            logger.warning("attempt %d/%d — unhandled exception: %s", attempt, attempts, exc)
            last = CheckResponse(Response="ERROR", Status="ERROR", error=str(exc), retryable=True)
            continue
        finally:
            _dec_active()

        resp = _build_response(res, shop_url)
        logger.info(
            "attempt %d/%d | status=%-8s code=%-24s elapsed=%.1fs",
            attempt, attempts, resp.Response, resp.status_code or "-",
            time.perf_counter() - t0,
        )
        if resp.Response in ("CHARGED", "APPROVED"):
            logger.info(
                "HIT | status=%s | amount=%s | site=%s | receipt=%s",
                resp.Response, resp.Price, shop_url, resp.receipt_url,
            )
        if not resp.retryable or attempt == attempts:
            return resp
        logger.info("retrying (retryable=true) …")
        last = resp

    return last


@app.get("/docs", include_in_schema=False)
async def custom_docs():
    return HTMLResponse(_DOCS_HTML)


@app.get("/health", tags=["meta"])
async def health():
    with _active_checks_lock:
        active = _active_checks
    return {
        "ok":            True,
        "threads":       THREAD_WORKERS,
        "retries":       MAX_RETRIES,
        "active_checks": active,
        "version":       "2.0.2",
    }


@app.get("/check", response_model=CheckResponse, tags=["check"])
async def check_get(
    card:  str = Query(..., description="Card string: number|mm|yyyy|cvv"),
    url:   str = Query(..., description="Shopify store URL"),
    proxy: str = Query(..., description="Proxy: http://user:pass@host:port"),
    low:   str = Query(default="true", description="true = prefer products under $5"),
):
    card_val, err = _validate_card(card)
    if err:
        err.CC = card
        return err
    url_val, err = _validate_url(url)
    if err:
        err.CC = card
        err.Site = url
        return err
    proxy_val, err = _validate_proxy(proxy)
    if err:
        err.CC = card
        err.Site = url_val
        return err
    low_mode = low.strip().lower() in ("1", "true", "yes")
    return await _run_check(url_val, card_val, proxy_val, low_mode)


@app.post("/check", response_model=CheckResponse, tags=["check"])
async def check_post(req: CheckRequest):
    raw_card = req.card or ""
    raw_url  = req.shop_url or ""
    card_val, err = _validate_card(raw_card)
    if err:
        err.CC = raw_card
        return err
    url_val, err = _validate_url(raw_url)
    if err:
        err.CC   = raw_card
        err.Site = raw_url
        return err
    proxy_val, err = _validate_proxy(req.proxy or "")
    if err:
        err.CC   = raw_card
        err.Site = url_val
        return err
    return await _run_check(url_val, card_val, proxy_val, req.low)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    logger.info("CardCheckout API — port=%d threads=%d retries=%d",
                port, THREAD_WORKERS, MAX_RETRIES)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
