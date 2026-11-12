---
name: "printful-v2-adapter"
description: "Integrate Printful API v2 for custom print-on-demand in Python/FastAPI: catalog cache, print-file rendering, draft-then-confirm orders, signed webhooks, rate limits."
---

# Printful v2 adapter

Use this when a custom site (not Shopify or WooCommerce) sells print-on-demand products through Printful: a custom apparel designer, merch built from an artwork gallery, or any order that has to reach Printful from your own backend. It covers the facts that bite, the adapter shape, rendering the print file yourself, the order flow, webhooks and tests. It fits the AI DevKit `print-on-demand` module (FastAPI + async SQLAlchemy + Postgres + a job worker + S3-compatible storage).

**Facts were checked against Printful's v2 docs on 2026-11-12. v2 is labelled beta, though Printful says its endpoints are usable in production. Re-check anything marked "verify" before relying on it, and prove every flow with draft orders before going live.**

## Facts that matter

- **Base URL:** `https://api.printful.com/v2/`. **Auth:** `Authorization: Bearer <private token>`. Legacy API keys no longer work.
- **Store header:** `X-PF-Store-Id` is needed only with an account-level token; a store-level token ignores it.
- **Rate limit:** 120 requests per 60 seconds, as a leaky bucket. Responses carry `X-Ratelimit-Limit`, `X-Ratelimit-Remaining`, `X-Ratelimit-Reset` and `X-Ratelimit-Policy`; a 429 carries `retry-after`.
- **Mockup generator:** about 2 tasks a minute for a new store and 10 once it has $10 of fulfilled orders (October 2026 research; verify). Too slow for live previews, so draw previews in the browser and call the generator once at checkout.
- **No rotation parameter.** Layer positions are `width`, `height`, `top`, `left` in inches from the print area's top-left corner, up to 5 layers per placement, file layers only. So render the whole print area yourself and place it at 0,0.
- **Files are fetched by URL and processed asynchronously** (`waiting`, then `ok` or `failed`). Sending a URL identical to an earlier file returns the old file, so put a version in every print-file URL.
- **Orders:** `external_id` is your order id, and order paths accept `@<external_id>` in place of Printful's id. Create the order as a draft, wait for `costs.calculation_status` to go from `calculating` to `done` (the `order_updated` webhook fires when it does), then confirm.
- **Print rules:** at least 150 DPI for apparel and no more than about 300; sRGB transparent PNG for DTG. New DTG products use `front_large` (15 x 18 in, about 2250 x 2700 px at 150 DPI); older ones use `front` (12 x 16 in, 1800 x 2400 px). Read the real print area per product from the catalog instead of hard-coding it.
- **Billing:** Printful charges the owner's Printful Wallet or card, separately from what the customer paid the owner. An unfunded wallet makes orders fail, so keep auto-recharge on.

## Endpoints used

| Purpose | Call |
| --- | --- |
| Catalog | `GET /v2/catalog-products`, `GET /v2/catalog-products/{id}`, `GET /v2/catalog-products/{id}/catalog-variants`, `GET /v2/catalog-variants/{id}` |
| Print areas and mockup styles | `GET /v2/catalog-products/{id}/mockup-styles` |
| Shipping quote | `POST /v2/shipping-rates` |
| Cost estimate | `POST /v2/order-estimation-tasks`, then `GET /v2/order-estimation-tasks?id=...` |
| Orders | `POST /v2/orders` (draft), `GET /v2/orders/{id}` or `/v2/orders/@{external_id}`, `POST /v2/orders/{id}/confirmation` |
| Mockups | `POST /v2/mockup-tasks`, `GET /v2/mockup-tasks?id=...` |
| Webhooks | `GET`, `POST`, `DELETE /v2/webhooks`; per event `GET`, `POST`, `DELETE /v2/webhooks/{eventType}` |

## Adapter shape

Keep the shop provider-agnostic. Printful is one implementation of a small protocol, so adding Printify or Gelato later doesn't touch the shop.

```python
from typing import Protocol

class PodProvider(Protocol):
    async def sync_catalog(self) -> None: ...
    async def print_area(self, product_id: int, placement: str) -> "PrintArea": ...
    async def quote_shipping(self, recipient: dict, items: list[dict], currency: str) -> list[dict]: ...
    async def create_draft(self, order: "ShopOrder", print_files: dict[str, str]) -> str: ...
    async def confirm(self, provider_order_id: str) -> None: ...
    async def get(self, external_id: str) -> dict: ...
    def verify_webhook(self, raw_body: bytes, headers: dict[str, str]) -> bool: ...
```

## Client with rate limiting and retries

```python
import asyncio
import time

import httpx

class LeakyBucket:
    """Spaces requests evenly, staying under Printful's 120 per minute."""
    def __init__(self, per_minute: int = 110):
        self.interval = 60 / per_minute
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if delay:
            await asyncio.sleep(delay)

class PrintfulClient:
    def __init__(self, token: str, store_id: str | None = None):
        headers = {"Authorization": f"Bearer {token}"}
        if store_id:
            headers["X-PF-Store-Id"] = store_id
        self.http = httpx.AsyncClient(base_url="https://api.printful.com/v2",
                                      headers=headers, timeout=httpx.Timeout(20.0))
        self.bucket = LeakyBucket()

    async def request(self, method: str, path: str, **kwargs) -> dict:
        for attempt in range(5):
            await self.bucket.wait()
            response = await self.http.request(method, path, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                await asyncio.sleep(min(float(response.headers.get("retry-after", 2 ** attempt)), 60))
                continue
            response.raise_for_status()
            return response.json()
        response.raise_for_status()
        raise RuntimeError("Printful kept failing after 5 attempts")
```

Run Printful calls only from the job worker, never inside a customer's request. The token is a secret: seal it at rest and never log it.

## Rendering the print file

Store the customer's design as normalized numbers relative to the print area, so it survives a provider switch: `placement`, `cx` and `cy` (center, 0 to 1), `scale` (art width divided by print-area width) and `rotation` (degrees clockwise).

```python
from io import BytesIO

from PIL import Image

def render_print_file(art: Image.Image, area_w_in: float, area_h_in: float, dpi: int,
                      cx: float, cy: float, scale: float, rotation: float) -> tuple[bytes, float]:
    width_px, height_px = round(area_w_in * dpi), round(area_h_in * dpi)
    art = art.convert("RGBA")
    target_w = max(1, round(width_px * scale))
    target_h = max(1, round(art.height * target_w / art.width))
    effective_dpi = art.width / (target_w / dpi)      # warn the customer below 150
    art = art.resize((target_w, target_h), Image.Resampling.LANCZOS)
    if rotation:
        art = art.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=True)
    canvas = Image.new("RGBA", (width_px, height_px), (0, 0, 0, 0))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(art, (round(cx * width_px - art.width / 2), round(cy * height_px - art.height / 2)))
    canvas = Image.alpha_composite(canvas, layer)
    out = BytesIO()
    canvas.save(out, "PNG", dpi=(dpi, dpi))
    return out.getvalue(), effective_dpi
```

- Convert artwork with an embedded color profile to sRGB first (Pillow's `ImageCms`).
- Pasting onto a separate layer clips art that hangs off the edge instead of failing on negative offsets.
- Upload the PNG to a public, unguessable, versioned URL that lives as long as the order, then send a layer covering the full area: `left` 0, `top` 0, `width` and `height` equal to the print area in inches.

## Order flow

1. **Quote** shipping before the customer pays (`/v2/shipping-rates`) and show retail plus shipping plus tax.
2. **Charge** through the site's payment provider. The customer pays the owner; there is no split payment.
3. **On the payment-succeeded event**, a job renders and uploads each print file, then creates a draft order with `external_id` set to your order id. Retrying with the same `external_id` must never create a second order: look it up with `GET /v2/orders/@{external_id}` first.
4. **Wait for costs** (`order_updated` webhook, or poll as a fallback). Compare Printful's cost to the price charged; if the margin is below the owner's floor, hold the order and alert instead of confirming.
5. **Confirm** with `POST /v2/orders/{id}/confirmation`.
6. **On failure**, retry with backoff, alert the owner, and refund the customer automatically after a set number of hours. Stripe's manual capture (authorize at checkout, capture after Printful accepts) is an alternative; card authorizations usually last about 7 days.

The order body nests items with `placements`, each with `placement`, `technique` (such as `dtg`) and `layers`. Check the exact field names against the v2 order schema (verify) and prove them with a draft order before the first sale.

## Webhooks

- One webhook configuration is active per token; `POST /v2/webhooks` replaces the previous one. A configuration can carry `expires_at`; leave it null so it doesn't lapse, and check it in the admin's health page.
- The configuration response returns `secret_key` in hex. Each event arrives with `x-pf-webhook-signature` (hex HMAC-SHA256) and `x-pf-webhook-public-key`.
- The docs say the HMAC covers the event data without naming the exact bytes (verify). Start by signing the raw request body, confirm with a real test event, then lock that in with a test.

```python
import hashlib
import hmac

def verify_printful(raw_body: bytes, signature_hex: str, secret_hex: str) -> bool:
    expected = hmac.new(bytes.fromhex(secret_hex), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_hex.strip().lower())
```

- There is no timestamp header to build a replay window from, so de-duplicate: store a hash of each processed body and ignore repeats.
- Useful events: `order_updated` (costs ready), `order_failed`, `order_canceled`, `order_put_hold`, `order_refunded`, `shipment_sent` (tracking), `shipment_delivered`, `shipment_returned`, `catalog_price_changed`, `catalog_stock_updated`, `mockup_task_finished`.
- Acknowledge fast with a 200 and do the work in a job.

## Catalog cache

- Sync the owner's curated products and variants into your own tables nightly, and on `catalog_price_changed` and `catalog_stock_updated`.
- The storefront and the designer read only your cache, never Printful live.
- Hide a variant the moment it goes out of stock; re-check price at checkout.

## Before the first sale (tell the owner)

- The owner is the seller of record and owes sales tax. Printful also charges the owner tax unless a resale certificate is on file first.
- Returns cover misprints only; chargebacks fall on the owner.
- Every gallery image needs commercial rights for merchandise.
- Keep the Printful Wallet funded with auto-recharge.

## Tests that must exist

- Signature check passes for a recorded real event and fails for a changed body or wrong secret.
- A repeated webhook body is processed once.
- Golden-image test: a known design renders the art at the expected pixel box, rotation included, and the PNG carries the DPI.
- Low-DPI art is flagged below 150 effective DPI.
- The same `external_id` never produces two Printful orders, even when the job retries.
- Draft, costs done, confirm: the state machine refuses to confirm before costs are `done` or below the margin floor.
- 429 with `retry-after` waits and retries; the bucket never exceeds 120 a minute in a burst test.

## In the AI DevKit

- Module id `print-on-demand`; requires `shop` and `payments`; the apparel designer is its web binding (react-konva editor storing `placement, cx, cy, scale, rotation`).
- Settings: Printful token and store id (secret), markup, curated products, margin floor, refund-after hours.
- Events: listens to `payments.checkout.completed`; emits `pod.order.submitted`, `pod.order.shipped`, `pod.order.failed`.
- Notifications: `pod.order_shipped` (customer, with tracking), `pod.order_failed` (owner).