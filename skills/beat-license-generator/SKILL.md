---
name: "beat-license-generator"
description: "Issue beat and composition license agreements (lease tiers, exclusives, sync quotes) as PDFs with license IDs, frozen terms and a verify page, in a Python/FastAPI store."
---

# Beat license generator

Use this when a site sells usage rights to music: beat leases, exclusive rights, or custom sync licenses for compositions. It covers the data model, issuing a license after payment, the PDF, the public verify page, exclusive-sale safety and the tests. It is written for a FastAPI + async SQLAlchemy + Postgres backend (the AI DevKit `licensing` module), but the logic ports anywhere.

**Not legal advice.** This skill turns owner-approved templates into documents. The owner sets every term and price, and a lawyer writes or reviews each template before it sells anything. Never invent legal terms for the owner; leave a clearly marked placeholder and ask.

## Core rules

1. **Terms are frozen at sale.** Every issued license stores a snapshot of its tier and the exact rendered text, plus the text's SHA-256. Editing a tier or template later never changes a license already sold.
2. **Templates and tiers are versioned.** A new edit makes a new version; old versions stay readable forever.
3. **The buyer accepts the exact text.** Checkout shows the rendered terms for that buyer and tier, records the acceptance (time, IP, user agent, terms hash), and the issued license's hash must match it.
4. **An exclusive can only sell once.** Hold it at checkout, enforce it with a database constraint, and refund the loser of any race.
5. **Full files never leak.** Previews are tagged or shortened files. Masters, WAVs and stems are delivered only through short-lived signed links after payment.

## Data model

| Table | Holds |
| --- | --- |
| `licensing_work` | A beat or composition: title, BPM, key, genre, moods, contributors and their shares, status (`for_sale`, `exclusive_pending`, `sold_exclusive`, `withdrawn`) |
| `licensing_work_file` | Files by format: `preview`, `mp3`, `wav`, `stems`; storage keys, never public URLs |
| `licensing_tier` | Versioned tier definitions (schema below) |
| `licensing_template` | Versioned agreement templates (Markdown with Jinja2 placeholders) |
| `licensing_acceptance` | Checkout acceptance: order id, terms hash, time, IP, user agent |
| `licensing_license` | Issued licenses: license id, order id, work id, licensee legal name, artist name, email, tier snapshot JSON, template version, rendered text, text SHA-256, PDF storage key, issued time (UTC), status (`active`, `revoked`) |
| `licensing_sync_request` | Custom license requests: use, media, territory, term, budget, status, the owner's quote |

A partial unique index makes a second exclusive impossible:

```sql
CREATE UNIQUE INDEX licensing_one_exclusive_per_work
  ON licensing_license (work_id)
  WHERE exclusive AND status = 'active';
```

## Tier schema

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict

class TierLimits(BaseModel):
    model_config = ConfigDict(strict=True)
    audio_streams: int | None          # None means unlimited
    units_sold: int | None
    music_videos: int | None
    monetized_video_streams: int | None
    radio_stations: int | None
    paid_performances: int | None

class LicenseTier(BaseModel):
    model_config = ConfigDict(strict=True)
    key: str                            # "basic", "premium", "trackout", "unlimited", "exclusive"
    name: str
    version: int
    files: list[Literal["mp3", "wav", "stems"]]
    price_cents: int
    currency: str = "USD"
    exclusive: bool = False
    term_years: int | None = None       # None means perpetual
    limits: TierLimits
    credit_line: str = "Prod. by {{ producer_names }}"
    writer_share_pct: int               # licensee's writer share, set by the owner
    publisher_share_pct: int
    sync_allowed: bool = False
    content_id_allowed: bool = False
```

A common ladder is basic (MP3), premium (MP3 + WAV), trackout (+ stems), unlimited (all files, no caps) and exclusive (sole rights). Treat it as a starting point the owner edits, never as defaults to ship.

## Template

Templates are Markdown with `## ` headings and Jinja2 placeholders. Render with `StrictUndefined`, so a missing field fails loudly instead of printing a blank into a contract. The starter below is a skeleton for the lawyer to fill, not usable terms:

```markdown
## Parties
This agreement is between {{ licensor_name }} ("Licensor") and {{ licensee_legal_name }}, performing as {{ licensee_artist_name }} ("Licensee").

## Work
"{{ work_title }}" produced by {{ producer_names }}. License ID {{ license_id }}, issued {{ issued_date }}.

## Grant
[LAWYER: grant wording for the {{ tier_name }} tier. Exclusive: {{ exclusive }}.]

## Limits
Audio streams: {{ limits.audio_streams or "unlimited" }}. Units sold: {{ limits.units_sold or "unlimited" }}. Music videos: {{ limits.music_videos or "unlimited" }}.

## Credit
Licensee credits the work as "{{ credit_line }}".

## Ownership and publishing
[LAWYER: master ownership and the split: writer {{ writer_share_pct }}%, publisher {{ publisher_share_pct }}%.]

## Restrictions
[LAWYER: no resale of the beat, sync only if {{ sync_allowed }}, Content ID only if {{ content_id_allowed }}, samples.]

## Term
{% if term_years %}{{ term_years }} years from the issue date.{% else %}Perpetual.{% endif %}

## Acceptance
Accepted electronically at checkout on {{ accepted_at }} (terms hash {{ terms_hash_short }}).
```

Lines starting `[LAWYER:` must be gone before a template can be published; add a check that refuses to activate any template containing that marker.

## Issuing a license

Run this as a background job on the payment-succeeded event (in DevKit, `payments.checkout.completed`), never inside the webhook request.

1. Load the order, the work, the tier version and the template version that the buyer accepted.
2. Lock the work row (`SELECT ... FOR UPDATE`). For an exclusive, confirm it's still `exclusive_pending` for this order.
3. Render the text, hash it, and check the hash equals the acceptance record's.
4. Make the license id, build the PDF, store it privately.
5. Insert the license (the unique index guards exclusives). Mark an exclusive work `sold_exclusive` and take it off the store.
6. Create the download entitlement for the tier's files.
7. Email the buyer the PDF and their download link; emit `licensing.license.issued`.
8. Audit the issue. If the insert fails on the exclusive index, refund the payment and tell the owner.

```python
import base64
import hashlib
import secrets
from io import BytesIO
from xml.sax.saxutils import escape

from jinja2 import Environment, StrictUndefined
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_env = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)

def new_license_id(prefix: str = "LIC") -> str:
    """80 random bits as 16 base32 characters: readable, and not guessable or countable."""
    raw = base64.b32encode(secrets.token_bytes(10)).decode()
    return f"{prefix}-{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"

def render_terms(template_text: str, context: dict) -> tuple[str, str]:
    text = _env.from_string(template_text).render(**context)
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()

def terms_to_pdf(text: str, title: str, license_id: str) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, title=title)
    styles = getSampleStyleSheet()
    story = [Paragraph(escape(title), styles["Title"]),
             Paragraph(f"License ID: {escape(license_id)}", styles["Normal"]),
             Spacer(1, 12)]
    for block in text.strip().split("\n\n"):
        if block.startswith("## "):
            heading, _, body = block.partition("\n")
            story.append(Paragraph(escape(heading[3:]), styles["Heading3"]))
            block = body
        if block:
            story.append(Paragraph(escape(block).replace("\n", "<br/>"), styles["BodyText"]))
        story.append(Spacer(1, 6))
    doc.build(story)
    return buf.getvalue()
```

ReportLab's `Paragraph` reads a small XML markup, so every value is escaped before it goes in.

## Exclusive sales

- When checkout starts for an exclusive, set the work to `exclusive_pending` with this order id and an expiry equal to the checkout session's. Other buyers see it as unavailable meanwhile.
- A job releases expired holds back to `for_sale`.
- The partial unique index is the last line of defence; a losing payment is refunded automatically.
- Leases sold before the exclusive keep their terms. Say so in the exclusive template, worded by the lawyer.

## Verify page

`GET /license/{license_id}` is public and shows only the work title, tier name, licensee artist name, issue date and status. Never the email, legal name or price. Rate-limit it, return the same 404 for unknown and malformed ids, and mark it `noindex`.

## Sync and custom licenses

Compositions for film, ads or games get a "request a license" form instead of a price: use, media, territory, term and budget. The owner replies with a quote, which creates a one-off tier version and a checkout link that expires. From payment on, the flow is the same as above.

## Collective splits

Each work lists contributors with shares that add up to 100. Store each sale's split on the license at issue time and report earnings per person. Payouts stay manual unless the owner chooses a payout provider.

## Tests that must exist

- Editing a tier or template after a sale leaves the issued license's text, hash and PDF unchanged.
- A template with a missing field fails to render (StrictUndefined); a template with `[LAWYER:` can't be activated.
- The acceptance hash and the issued hash match; a mismatch blocks issuing.
- Two concurrent exclusive purchases: exactly one license issues, the other payment is refunded.
- The verify page never returns the email, legal name or price, and answers unknown ids with the same 404.
- Download links for WAV and stems exist only after payment and expire.
- The PDF contains the license id, work title, tier name and licensee artist name.

## In the AI DevKit

- Module id `licensing`; requires `shop`, `payments`, `downloads`; works with `audio-player` for previews and `campaigns` for free-download-for-email.
- Permissions: `licensing.work.manage`, `licensing.tier.manage`, `licensing.license.revoke`.
- Events: emits `licensing.license.issued`, `licensing.work.sold_exclusive`; listens to `payments.checkout.completed`, `payments.refund.issued`.
- Notifications: `licensing.license_issued` (buyer), `licensing.sync_request_received` (owner).