<!-- Copied from VM Website/design/specs/backend-plan.md on 2026-11-15. The VM Website copy is the source; update both. -->

# Vibrant Mindz backend: plan

2026-11-15. The backend is built as MechFrame modules on the MechFrame kernel. Vibrant Mindz is the first site that installs them.

**Already settled; this plan doesn't repeat it:** `docs/plans/vibrant-mindz-module-plan.md` covers the 17 modules, how they fit, and the owner's answers Q1–Q6 (2026-11-13). This file adds what the homepage design changed, the admin map, and the build order that follows.

## 1. Scope of the first build (owner, 2026-11-15)

All four areas: **music and players**, **people and access**, **marketplace**, **community and profiles**.

| Area | Modules | Status |
| --- | --- | --- |
| Music and players | `discography`, `audio-player`, `featured` (new), `embeds` | `embeds` lifted from VybeSite; the rest new |
| People and access | kernel `auth`, `users`, `roles`, `audit`, `security` | Kernel K2 underway (passwords, sessions and TOTP done; passkeys next) |
| Marketplace (Vibrified Marketplace) | `payments`, `shop`, `downloads`, `licensing`, `print-on-demand` | `payments`, `shop` and `downloads` planned in VybeSite; `licensing` new |
| Community and profiles | `roster`, `portfolio`, `community`, `comments`, `reactions` | `community` and `reactions` ported from VybeMindz; the rest new |
| Already in the plan for content | `pages`, `blog`, `contact`, `campaigns`, plus `media` (the media library, which `blog` requires and the `artist-or-band` recipe lists) | Lifted from VybeSite |

## 2. What the homepage design adds to the module plan

1. **New module: `featured`** (S). Named slots, each holding an ordered list of placements, with optional `starts_at` and `ends_at`. A placement points at another module's item as `{module, type, id}`, with no foreign key (SPEC 10), or holds a plain link. It's generic, so any site can use it for featured products, posts or anything else.
   - Vibrant Mindz slots: `spotlight` (discography tracks), `releases` (discography albums), `videos` (YouTube links).
   - It's the Admin › Homepage › Players screen. Full detail in `design/specs/players-admin.md`.
2. **`audio-player` moves up to launch.** The homepage spotlight and the Releases deck need it on day one. The beat store's tagged previews stay with `licensing` (step 5).
3. **`discography` gets an audio source per track:** an upload (kept in R2; a job makes the stream file and the waveform peaks) or an external SoundCloud link, with a site default in Settings.
4. **The YouTube playlist player is a component of `embeds`** (`web/public.ts`), which the homepage uses for the `videos` slot (spec `design/specs/videos-player.md`). Member-only video waits for `video` and `memberships` (roadmap wave 2c).
5. **The marketplace's 8 tiles map to modules:**

| Tile | Module | Notes |
| --- | --- | --- |
| Beats | `licensing` | Lease tiers (Q1); delivered through `downloads` |
| CDs, Vinyl, Poetry books | `shop` | Physical products with shipping |
| Paintings | `shop` | Stock of 1; links to the piece in `portfolio` |
| Exclusive videos | `downloads` | Paid downloads in v1 (Q2) |
| Apparel | `print-on-demand` | The designer plus Printful (step 6) |
| Rap battles | `shop` + `downloads` | **Assumed for v1:** rap battle videos sold as downloads. Live battles with entries and voting come with `contests` (roadmap wave 2b) |

6. **Roles on this site.** Built in: owner, admin, editor, member. One custom role, **artist**, is for the seven collective members. Artists edit their own roster profile, portfolio pieces and beats; modules check this with `require_owner_or(permission)`. Staff and artists must have a second factor (SPEC 14.1).

## 3. Admin map

The sidebar comes from each module's `nav.admin` slot, and the dashboard cards from `admin.dashboard.widget`. Every page follows the owner's lens (SPEC 8): what's wrong, why it matters and what to do, with detail one click deeper.

| Sidebar | Pages | Module | Permission (`<id>.<resource>.<action>`) |
| --- | --- | --- | --- |
| Dashboard | Setup checklist, needs attention, now playing, sales, new members | kernel + widgets | staff |
| Homepage › Players | Spotlight, Releases, Videos | `featured` | `featured.placement.manage` |
| Music | Albums, Tracks, Credits | `discography` | `discography.release.manage` |
| Beats | Works, License tiers, Licenses issued | `licensing` | `licensing.work.manage`, `licensing.tier.manage` |
| Marketplace | Products, Orders, Downloads, Apparel, Payments | `shop`, `downloads`, `print-on-demand`, `payments` | `shop.product.manage`, `shop.order.manage`, `payments.settings.manage` |
| Collective | Members, Portfolio | `roster`, `portfolio` | `roster.profile.manage`, `portfolio.piece.manage` |
| Community | Channels, Moderation queue, Comments to approve | `community`, kernel `moderation`, `comments` | `community.channel.manage`, `kernel.moderation.act`, `comments.comment.approve` |
| Content | Pages, Blog, Newsletter, Inbox | `pages`, `blog`, `campaigns`, `contact` | per module |
| People and access | People, Roles and permissions, Invites, Audit log | kernel | `auth.user.manage`, `auth.role.assign` |
| Settings | Site, Features (module switches), System (jobs, dead letters) | kernel + `admin.settings.section` | owner, admin |

The canvas **Admin** page draws six of these: Dashboard, Players, Album editor, Products, Member profile, and Roles and permissions.

## 4. Build order (revised from the module plan's section 11)

1. **Kernel to K2 done** (passkeys), plus `media`, `pages`, `blog`, `embeds`, `contact` and `campaigns`, lifted from VybeSite.
2. **`discography`, `audio-player` and `featured`.** The homepage players are now real, managed in Admin › Players.
3. **`roster`, `portfolio`, `comments` and `reactions`.** The content side is complete.
4. **`community`**, ported from VybeMindz.
5. **`payments`, `shop` and `downloads`.** This is MechFrame's v1.0 gate. **The site launches here.**
6. **`licensing`:** the beat store opens.
7. **`print-on-demand`:** the apparel designer opens.

**Owner decisions, 2026-11-17** (recorded here 2026-11-18 from the VM Website session; its `design/specs/backend-plan.md`, section 4, is the source; the options that lost are in brackets):

- **One primary-button hover, site and admin:** `#FF9447` (the admin boards used `#FF8C3D`; all 26 now use `#FF9447`). For K4's admin shell: the primary action hovers to the theme's accent-hover, as on the site. Brief: VM Website `design/specs/admin-look.md`, "The shell as drawn". [Keeping both; making the site match the admin.]
- **A Videos page at `/videos`, built in step 2** with `discography`, `audio-player` and `featured`: the homepage's player plus every video in the `featured` slot `videos` (`GET /api/featured/slots/videos`, the same list as the homepage's Videos section, which stays and links to it), filtered by a new optional column `featured_placement.video_kind` (`'music-video' | 'rap-battle' | 'poetry'`, confirmed by the owner on 2026-11-18). Admin › Homepage › Players › Videos gets a Kind menu per video. Specs: VM Website `design/specs/players-admin.md` (data model, admin), `videos-player.md` ("The Videos page"), `site-pages.md` (the Videos row); boards `design/site/Videos.dc.html` and `AdminPlayers.dc.html`. [The homepage section alone.]
- **Payment methods at launch (step 5):** cards, Apple Pay and Google Pay, all on Stripe's hosted Checkout, which shows the wallets with no extra build. Hosted Checkout needs no domain registration for Apple Pay: Stripe asks for that only with Elements or embedded Checkout (docs.stripe.com/apple-pay and /payments/payment-methods/pmd-registration, checked 2026-11-18). So launch has no extra step; a domain step added on 2026-11-17 was a mistake and came off Admin › Marketplace › Payments on 2026-11-18 (the owner), whose launch checklist has five steps. PayPal stays a later provider. Board: `AdminPayments.dc.html`. [Cards only; cards, wallets and PayPal at launch.]
- **Steps 6 and 7 are designed after launch:** the beat store and the apparel designer get their screens once the site is live. [Designing them now.]

**Owner answers, 2026-11-18** (from the VM Website sessions; the same source, section 4):

- **The video kinds are confirmed:** `music-video`, `rap-battle` and `poetry` (Music videos, Rap battles, Poetry).
- **Links from new community members are held** for a moderator for their first 7 days (step 4, `community`; the Channels and Moderation boards draw it; the owner picked 7 on 2026-11-18, afternoon). [Dropping the rule; the link filter alone.]
- **"petro" on Catalyst is petroTHAdestroyer.** The site's seed links that credit to the petroTHAdestroyer profile, so Catalyst shows there. The Credits board (`AdminCredits.dc.html`) still draws the credit unlinked, which is how the screen looks before someone links it.

**For K4:** the site's theme, VM Website `design/theme/vibrant-mindz/`, holds every value the 44 canvas boards use (a census test there fails on a value the theme lacks). Its README's "At K4" says how it moves: copy `tokens.json`, `tokens.css` and the generator; rename the tokens to Machined Light's names; the census stays in the VM Website folder and is rerun after the rename, so no value changes.

## 5. What the scaffold zip holds

- For each **new** module (`featured`, `discography`, `audio-player`, `roster`, `portfolio`, `comments`, `licensing`): a filled `module.json`, `MODULE.md`, model, schema and router stubs following `modules/_template`, and contract-test stubs.
- For each **lifted or ported** module (`media`, `pages`, `blog`, `embeds`, `contact`, `campaigns`, `community`, `reactions`, `payments`, `shop`, `downloads`, `print-on-demand`): a filled `module.json` and `MODULE.md`, plus an extraction brief naming the source paths, for the `mechframe-module-extractor` skill.
- `KICKOFF.md`: the order above, one Claude Code session per step, each ending with `mechframe check` green.
