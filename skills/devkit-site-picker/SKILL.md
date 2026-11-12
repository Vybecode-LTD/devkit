---
name: "devkit-site-picker"
description: "Turn a short site brief into an AI DevKit build plan: ask at most 3 questions, match a recipe, pick modules from the catalog with reasons, check dependencies and conflicts, and produce the devkit commands."
---

# DevKit site picker

Use this whenever a new site starts on the AI DevKit, or someone asks "what modules does this site need?". Input is a few sentences about the site, sometimes with the address of a site it replaces. Output is a confirmed module list with reasons, then the commands and settings to build it.

The DevKit spec (`SPEC.md`, section 17) and the repo's `AGENT-GUIDE.md` define this flow. Re-read them first; where they differ from this skill, they win. If the `devkit` CLI isn't built yet, do its steps by hand as spec section 12 describes.

## What to read, and what not to

- Read `AGENT-GUIDE.md`, `catalog.json` and every file in `recipes/`.
- The catalog alone is enough to pick. Open a module's `MODULE.md` only for finalists, or when two modules both seem to fit.
- Never read module source code to decide.

## Step 1: the brief card

Turn the brief into this card. Fill only what the brief says; mark the rest unknown.

| Field | Answer |
| --- | --- |
| Purpose | One sentence |
| Visitors | Who comes, and why |
| Content | What the site publishes (posts, music, video, art, products, docs) |
| Accounts | Do visitors sign in? Who: members, customers, staff only? |
| Money | Does money change hands? For what: physical goods, digital files, usage rights, custom merch, subscriptions, donations, bookings |
| Interaction | Comments on content, real-time chat, forum threads, reviews, none |
| Integrations | Services named: Stripe, PayPal, Printful, YouTube, SoundCloud, mail providers |
| Sensitive | Minors, health, legal, money handling, private messages |
| Launch vs later | What must exist at launch, what can follow |

If the site replaces an existing one, read that site first. Its pages and features are requirements even when the brief doesn't mention them (a gallery, solo artist pages, a credits page).

## Step 2: ask, at most 3 questions

Ask only questions whose answer changes the module list, in this order of value:

1. Do visitors get accounts, and for what?
2. Does money change hands, and for what kinds of thing?
3. Do visitors talk to each other or under content, and how?

Use tappable multiple-choice questions where the interface has them. With no one there to answer, assume the conservative default (no accounts, no money, no interaction), say so at the top of the plan, and carry on.

## Step 3: match a recipe

Compare the brief card with each recipe's `fits` lines. Take the closest; if none is close, start from `minimal`. The recipe is a starting point, not the answer.

## Step 4: pick modules

For each catalog entry, test its `use_when` and `avoid_when` against the card. Then:

1. Add every module in each pick's `requires`, repeatedly, until nothing new appears.
2. Check `conflicts`. If two picks conflict, keep the one whose `use_when` matches better, and say why.
3. Prefer fewer modules. A module needs a sentence from the brief behind it.
4. Mark each pick `launch` or `later`, following the card's launch line.
5. Mark each pick's catalog status: `stable`, `experimental`, or missing.

**Distinctions agents get wrong**

| If the brief says | Pick | Not |
| --- | --- | --- |
| Videos or tracks hosted on YouTube, SoundCloud, Spotify, Bandcamp | `embeds` | `audio-player` |
| Selling or previewing the site's own audio files | `audio-player` | `embeds` |
| Discussion under posts or items | `comments` | `community` |
| Real-time chat, channels, a Discord-like space | `community` | `comments` |
| Long-lived topic threads that search engines should index | a forum module (if the catalog has one; otherwise a gap) | `community` |
| Selling usage rights to files (beats, samples, compositions) | `licensing` (with `shop`, `payments`, `downloads`) | `shop` alone |
| Customers designing their own printed products | `print-on-demand` | `shop` alone |
| Any money at all | `payments` | |
| Newsletters, release announcements | `campaigns` | |
| Visual work by discipline (paintings, design, animation) | `portfolio` | `blog` |
| A profile per member or artist | `roster` | `pages` |

Accounts are a cost, so add member sign-up only when a pick needs it (community, comments, downloads for registered customers, licensing). Note the sign-up mode the brief implies: open, invite-only or closed.

## Step 5: name the gaps

List every need that no module covers. For each, say one of:

- **Site code:** it's specific to this site, so it goes in `site/` folders.
- **Module candidate:** other sites would want it, so build or extract it as a module (see the `devkit-module-extractor` skill) and add it to the catalog.

## Step 6: present the plan and get a yes

```markdown
## <Site> build plan
**Brief card:** <the table>
**Assumed:** <anything assumed without an answer>
**Recipe:** <name>, then <changes to it>

| Module | Why (from the brief) | Phase | Status |
| --- | --- | --- | --- |

**Considered and dropped:** <module: reason from its avoid_when>
**Gaps:** <need: site code or module candidate>
**Settings to decide:** <sign-up mode, payment providers, theme>
```

Nothing is copied into the site until the owner confirms the list.

## Step 7: build commands

After the yes:

```
devkit new <site> --recipe <recipe>
devkit add <module>        # one per module added beyond the recipe
devkit remove <module>     # one per recipe module dropped
```

Then set the theme, each module's settings and the env vars the CLI prints. Write the site's `CLAUDE.md` with the brief card, the confirmed module list, the gaps and the decisions taken. Build the site's own pages in `site/` folders. Run `devkit check` and the tests, and report the exact commands and results.

## Worked example: Vibrant Mindz

**Brief:** an audio-visual collective's home (music, poetry, paintings, video, animation, graphic design) with a store for beats, merch and art and a community for fans, replacing a WordPress site.

**Picks at launch:** `pages`, `blog`, `embeds`, `contact`, `campaigns`, `comments`, `reactions`, `community`, `discography`, `portfolio`, `roster`, `payments`, `shop`, `downloads`.
**Later:** `licensing` and `audio-player` (the beat store), then `print-on-demand` (the apparel designer).
**Why not `audio-player` at launch:** releases play through `embeds` from SoundCloud and Spotify; the player is needed only once beats are sold from the site's own files.
**Gaps found:** none blocking; the solo artist pages became `roster`, the gallery became `portfolio`.

## Pitfalls

- Picking by keyword instead of by `use_when` and `avoid_when`.
- Forgetting `requires`, so a module installs without its base.
- Adding accounts or a community "in case".
- Ignoring the old site's existing pages.
- Building before the owner confirms the list.