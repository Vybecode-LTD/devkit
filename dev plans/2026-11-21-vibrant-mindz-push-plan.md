# Plan: from hook 4 to building Vibrant Mindz (2026-11-21)

**Goal:** in-depth work on the Vibrant Mindz site as soon as possible: its front end now, beside the framework, and its modules as soon as the hooks they need are in.

**Where it stands:** the kernel is done (K0 to K5) and hooks 1 to 3 are in (#97 to #99). The site has 44 boards, specs and a theme (`C:\DEV\VM Website`), but no app. Its step 1 modules (`media`, `pages`, `blog`, `embeds`, `contact`, `campaigns`) need hooks 4 to 8.

## The owner's decisions (2026-11-21, in chat)

1. **Hooks 9 and 10 wait.** Entitlements lands just before step 5 (`downloads`), and profile tabs before wave 2b (`profiles`). Step 1 starts right after hook 8. This amends decisions 0018 and 0052.
2. **Both projects run at once:** a Vibrant Mindz website session beside MechFrame's, one session per project, starting the site app now.
3. **`git init` in `C:\DEV\VM Website`, local only.** No GitHub repo until the owner says so.

## MechFrame track (`C:\DEV\AI-DevKit`), one session at a time

| Session | Work, in order | PRs (predicted) | Why this order |
| --- | --- | --- | --- |
| **M1 (next)** | **0.** The kit's two fixes from VM Website Dev 05 (below). **1.** Hook 4, seed data. **2.** Hook 5, bot check. **3.** Hook 6, consent (stretch) | #101 to #104 | The kit fix is small and the site uses it at once. Seed data is needed by every module; bot check by `contact`; consent by `embeds` |
| **M2** | Hook 7, export and erase: it builds 14.7's export, a job writing a ZIP to private storage and mailing a link. Hook 8, dashboard cards. Then decision 0052's Status: "1 to 8 applied" | 2 | `contact` and `campaigns` hold people's data. Step 5's checklist needs hook 8, and step 1's inboxes want "Needs you" items |
| **M3** | `mechframe upgrade` for the kernel: its one-page contract first, for the owner's approval. Then `media` (`blog` requires it) | 2 | The Vibrant Mindz site can then take the kernel's changes and add modules (the CLI has no upgrade yet: `cli/README.md`) |
| **M4** | `pages`, `blog` | 2 | |
| **M5** | `embeds` (with the YouTube playlist component; its one-plays-at-a-time hand-off to `audio-player` waits for step 2), `contact`, `campaigns` | 3 | Step 1 is done |
| Later | Hook 9 before step 5; hook 10 before wave 2b | | Decision 1 |

Each module is lifted with `mechframe-module-extractor`, linted with `module-contract-lint`, checked with VybeSite's brand check, and has its brief in `docs/plans/vibrant-mindz-backend/extraction/`.

**The kit's two fixes** (from VM Website Dev 05, 2026-11-21; the owner said "Send it now"; brief: `C:\DEV\VM Website\design\specs\admin-look.md`, "Control edges" and "Keyboard focus"):
- **A field's fill.** The boards fill every field with the page colour (`#070A16`, `color.canvas`). The kit's `.mf-input` uses `color.well`, which in Vibrant Mindz is `#04060D`, a shade darker. The fix is a field-fill role: Vibrant Mindz points it at canvas, Machined Light at its well. It goes through `themes/*/tokens.json`, `python -m tools.themes` and `themes/README.md`'s required tokens.
- **The gap ring on every switch.** An off switch's `#5C6584` track meets the 1px `#FF7A1F` ring at 2.2:1. So `.mf-switch:focus-visible` takes the gap ring on or off, not only `[aria-checked="true"]` (the `.mf-admin-look` gap rule, `kernel/web/src/ui/kit.css`, near line 1071).

## Vibrant Mindz track (`C:\DEV\VM Website`), alongside

| Session | Work | Done when |
| --- | --- | --- |
| **V1** | `git init` with a `.gitignore` (venv, `node_modules`, build output, `.env`; decide whether the two zips and `design/assets/originals` go in). From MechFrame's checkout (read only), `python -m mechframe new "C:\DEV\VM Website\vibrantmindz" --name "Vibrant Mindz" --theme vibrant-mindz`. A first green run: venv, migrations on a local database of its own, tests, `npm ci`, build, `mechframe check`, `create-owner`. Then the site's shell (header, footer, nav) and the homepage from `design/site/Main.dc.html`, into `web/src/site/`. The player sections run on typed stand-in data (`web/src/site/fixtures.ts`) until step 2's `/api/site/home`. The kernel's sign-in and account screens are checked against `Auth.dc.html` and `Account.dc.html` | The homepage matches its board at 1440 and 390 (rendered contrast too). Gaps in the kernel are listed for MechFrame |
| **V2** | The pages step 1 feeds (Blog, Post, Contact), then the layouts of Music, Release, Videos, Collective, Artist and Art, all on stand-in data shaped like the specs' answers (`design/specs/site-pages.md`) | Each page matches its board in its drawn states |
| **V3 on** | As each module lands on MechFrame `main`: refresh the kernel, `mechframe add <id>`, swap the stand-ins for the module's typed client, and write each public page's server copy (`backend/app/site/pages.py`). Seed with the site's seed in hook 4's shape | The page shows real data locally |

**Until `mechframe upgrade` exists,** the kernel is refreshed by making a fresh site with `mechframe new` and moving the site's own parts across: `backend/app/site/`, `web/src/site/`, the registries and `.env`. The site's code lives only there (its `CLAUDE.md`), so nothing else is lost. `site-additions/` (the seed and `/api/site/home`) is copied in once `featured` and `roster` exist (steps 2 and 3).

## The owner's track (any time; it unlocks real content)

- **Content to send** (`C:\DEV\VM Website\design\specs\content-intake.md`): items 1 to 9 and 16 to 17 for steps 1 to 3's pages (members' roles, photos, words and links; the Catalyst tracklist; credits; lyrics; the videos and the channel; the art pieces; the community channels). Items 10 to 15 before the shop.
- **To decide:** shipping origin, rates and times; the contact email; the share image; the email service at deploy.
- **To approve:** the `mechframe upgrade` contract (M3). Later, the site's GitHub repo and Railway project.

## How the MechFrame sessions go faster

- **Stack the PRs.** While one hook's CI runs, start the next on a branch from it. Once the first lands, merge `main` into the next (never force-push).
- **One full suite per PR,** in the background while the docs are written. Run the hook's own tests and a mutant script first.
- **#99 is the pattern:** `git show --stat 43d3934` lists every place a hook touches.
- **Settled ahead for hook 4,** each a "Changes after approval" line, told to the owner in its PR:
  - its contract test seeds through a test-support route, `POST /api/_test/seed`;
  - the site's own seed (`backend/app/site/seed.py`) runs last, after the modules, as the site's pages do (decision 0048).
- **Close out at a natural break past ~400K tokens,** with the starting prompt naming the next item.

## Between the two projects

- The Vibrant Mindz session never edits MechFrame's checkout, but may run its CLI.
- A kernel or kit gap it finds goes in its handoff's "For MechFrame" list, or in a message with the owner's OK. MechFrame's session reads that list at its start.
- MechFrame's session never edits `C:\DEV\VM Website`.

## Risks

- **Hook 7 is the largest hook** (a job, storage, mail and a signed link), and may take M2 alone.
- **Stand-in data can drift from a module's real answers.** It's typed from the specs, and each piece goes as its module lands.
- **The kernel changes under a kernel-only site.** The site's code is kept apart, as above.

**This plan is done when** step 1's six modules are on `main` and added to the Vibrant Mindz site, and its homepage and step 1 pages show real data locally.
