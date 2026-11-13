# Module roadmap after v1.0

The owner picked the modules on 2026-11-13 from a backlog of about 140 ideas (Must, Want, Later or Nah per module); the owner's picks and answers are the source of truth, and decision 0018 records them. Change a pick and this plan gets redone.

**The count:** 78 Must (76 picked, plus `maps` and `invoices` promoted on 2026-11-13), 17 Want, 39 Later, 4 Nah, plus `sms` marked "yes, but not via Twilio". All 7 framework tools are Must. The 12 contract hooks were settled separately (below).

Everything below runs after the Vibrant Mindz build in the module plan (kernel → content → community → payments/shop/downloads → v1.0 gate and launch → licensing and audio-player → print-on-demand). Each wave ends by running on a real site.

---

## The owner's answers (2026-11-13)

1. **Hooks.** The 10 hooks that Must modules need are Must. **i18n:** v1 adopts a "no hard-coded UI strings" rule; full translations are Later. **Flags:** Later, until A/B testing (`experiments`) is wanted; VybeSite's parts switch covers on/off meanwhile.
2. **SMS provider: chosen at wave 3b,** from a comparison researched then (the owner, 2026-11-13). `sms` is built as a provider adapter either way, so nothing waits on it until then.
3. **`maps` and `invoices` promoted to Must.** `maps` lands in wave 3b ahead of `directory` and `events`; `invoices` lands in wave 3a ahead of `client-portal`. `proposals` stays Later.
4. **No migration for Vibrant Mindz.** The new Vibrant Mindz site is built from scratch, so `migrate` stays in wave 3a for client sites.

---

## Wave 0: contract hooks (before v1.0 freezes)

| Hook | Musts that need it | Call |
|---|---|---|
| Search index | site-search, semantic-search, concierge, docs | Must |
| Consent categories | consent, analytics-adapters, social-feeds, video | Must |
| Entitlements | memberships, video member-only streams, ai-studio | Must |
| Bot check | bot-shield, forms, reviews, submissions | Must |
| Export and erase | privacy-center | Must; already in SPEC 5 and 10 (`data_hooks`), needs only an export contract test |
| Content lifecycle | editorial-calendar, drops, podcast, changelog, announcements | Must |
| Taxonomy | directory, recipes, docs, wiki | Must |
| Profile tabs | profiles | Must |
| Dashboard cards | setup-wizard, fleet | Must; builds on the `admin.dashboard.widget` slot (SPEC 8) |
| Seed data | catalog-site, visual-regression, theme-generator | Must |
| i18n | none | Rule now (no hard-coded UI strings); full i18n Later |
| Flags | experiments (Later) | Later |

Gate: each hook in SPEC.md with a passing contract test. Each one lands with the `devkit-hook-designer` skill: one repo decision record for the batch, one PR per hook.

## Framework tools: when each lands

| Tool | When | Why then |
|---|---|---|
| `provenance-scan`, `quality-gate` | Now, during v1 extraction | Code is being lifted from VybeSite right now |
| `visual-regression`, `catalog-site` | After wave 1 | Enough modules and seed data to show |
| `theme-generator`, `fleet` | Wave 3a | Second and third sites appear |
| `platform-bridge` | After wave 5 | Opens the desktop phase |

---

## Wave 1: foundations every site uses

Small, mostly S/M, and they unblock everything after. Proves it on: Vibrant Mindz right after launch.

| Module | Effort | Needs |
|---|---|---|
| `forms` | M | bot check hook |
| `bot-shield` | S | bot check hook |
| `consent` | M | consent hook |
| `analytics-adapters` | S | consent |
| `privacy-center` | M | export and erase hook |
| `legal` | S | none |
| `security-center` | M | kernel auth and audit |
| `account-center` | M | kernel auth |
| `site-search` | M | search hook |
| `redirects` | S | none |
| `data-grid` | M | UI kit |
| `import-export` | M | data-grid |
| `command-palette` | S | admin shell |
| `setup-wizard` | M | dashboard cards hook |
| `image-pipeline` | M | media library |
| `ai-gateway` | M | none |

Wants that fit here: `maintenance`, `jobs-dashboard`, `impersonation`, `a11y`.

## Wave 2a: sell more

Proves it on: the Vibrant Mindz store and fan memberships.

| Module | Effort | Needs |
|---|---|---|
| `memberships` | M | entitlements hook, payments |
| `credits` | M | payments |
| `discounts` | M | shop |
| `drops` | M | shop, lifecycle hook |
| `tips` | S | payments |
| `shipping` | M | shop |
| `pricing-table` | S | payments |
| `waitlist` | S | invites |

Wants that fit here: `courses` (after memberships).

## Wave 2b: fans and community

Proves it on: the Vibrant Mindz community, with beat and rap battles.

| Module | Effort | Needs |
|---|---|---|
| `profiles` | M | profile tabs hook |
| `follows` | S | profiles |
| `feed` | L | follows |
| `groups` | L | community |
| `polls` | S | port of VybeMindz polls |
| `bookmarks` | S | none |
| `reviews` | M | kernel moderation |
| `submissions` | M | forms, moderation |
| `contests` | L | submissions |
| `live` | M | community chat |
| `rooms` | L | port of an existing voice and video stack (`docs/private/inventory.md`) |

Wants that fit here: `web-push`.

## Wave 2c: music and media

Proves it on: the Vibrant Mindz music side.

| Module | Effort | Needs |
|---|---|---|
| `video` | M | memberships (member-only playback) |
| `radio` | M | audio-player |
| `podcast` | M | audio-player, lifecycle hook |
| `music-import` | S | discography |
| `press-kit` | S | none |
| `short-links` | S | analytics |
| `social-feeds` | S | consent |
| `transfer` | S | port of existing burn links (`docs/private/inventory.md`) |

## Wave 3a: agency handoff

Proves it on: the first agency client site.

| Module | Effort | Needs |
|---|---|---|
| `migrate` | L | redirects |
| `invoices` | M | payments |
| `client-portal` | L | invoices |
| `white-label` | S | themes |
| `onboarding-tours` | M | none |
| `crm` | L | contact, campaigns, shop |
| `reports` | M | analytics |
| `email-builder` | M | campaigns |
| `announcements` | S | lifecycle hook |
| `editorial-calendar` | M | lifecycle hook |
| `zapier` | M | spec events |

Wants that fit here: `preview-links`, `client-mode`, `automations`. Framework tools: `theme-generator`, `fleet`.

## Wave 3b: service businesses

Proves it on: a booking site (tattoo or studio).

| Module | Effort | Needs |
|---|---|---|
| `maps` | S | none |
| `booking` | L | payments |
| `events` | M | maps |
| `directory` | L | taxonomy hook, maps |
| `recipes` | M | taxonomy hook |
| `google-business` | S | none |
| `sms` | S | kernel notifications; provider TBD (decision 2) |

Wants that fit here: `calendar-sync`, `classes`, `age-gate`.

## Wave 4: software products

Proves it on: the CarbonDSP storefront.

| Module | Effort | Needs |
|---|---|---|
| `license-keys` | L | payments, downloads |
| `release-channels` | M | license-keys |
| `beta-program` | S | invites |
| `crash-reports` | M | none |
| `preset-exchange` | M | reviews, downloads |
| `docs` | M | search and taxonomy hooks |
| `faq` | S | none |
| `changelog` | S | lifecycle hook |
| `wiki` | L | taxonomy hook |
| `helpdesk` | L | docs |
| `public-api` | M | none |
| `orgs` | M | port of Basefra.me tenants |
| `enterprise-sso` | L | orgs |

Wants that fit here: `ideas`, `feedback`.

## Wave 5: AI layer

Proves it on: retrofitted into every site so far.

| Module | Effort | Needs |
|---|---|---|
| `semantic-search` | M | site-search |
| `concierge` | M | semantic-search, ai-gateway |
| `agent-ready` | M | search hook |
| `prompts` | M | ai-gateway |
| `ai-studio` | L | credits, ai-gateway |

Wants that fit here: `ai-enrich`, `ai-moderation`, `ai-forms`.

---

## Size check

78 Musts is a lot, but 64 of them are S or M, and the extraction pipeline (`devkit-module-extractor`, `module-contract-lint`) makes those quick. The time goes into the 14 L's: `migrate`, `client-portal`, `crm`, `booking`, `directory`, `feed`, `groups`, `contests`, `rooms`, `wiki`, `helpdesk`, `license-keys`, `enterprise-sso`, `ai-studio`.

## Parked

**Later (39):** badges, referrals, jobs, link-in-bio, testimonials, collections, qa, commissions, affiliates, crowdfunding, abandoned-cart, marketplace, tickets, waivers, reservations, proofing, before-after, surveys, popups, experiments, takedowns, identity-check, proposals, smart-links, tour-dates, lyrics, fan-requests, flash, aftercare, prints, city-alerts, clips, meal-plans, coaching, menu, locations, discord-sync, esign, accounting.

**Nah (4):** fan-wall, voice, 3d-viewer, email-sync.

## Skill ideas

`devkit-hook-designer` (in `skills/`) lands the wave 0 hooks. The skills the later waves want are in `docs/SKILL-BACKLOG.md`.
