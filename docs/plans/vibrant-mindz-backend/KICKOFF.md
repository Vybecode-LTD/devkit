# Vibrant Mindz backend: Claude Code kickoff

One Claude Code session per step, in this order. Every step ends with `python -m tools.validate_schemas` clean, the step's tests passing, and `devkit check` green. Read first: `AGENT-GUIDE.md`, `SPEC.md`, `docs/plans/vibrant-mindz-module-plan.md`, then this folder.

**Inputs in this folder:** `backend-plan.md` (scope and order), `players-admin.md` and `videos-player.md` (the homepage players), `admin-screens.md` (the six admin designs), `kernel-additions.md`, `extraction/*.md` (one brief per lifted or planned module). Admin and homepage designs: https://claude.ai/artifact/W7EZQumtcK36K3xczG8mNH. Scaffolded modules are already in `modules/`, each waiting as `modules/_<id>/` (`_featured`, `_discography`, `_audio-player`, `_roster`, `_portfolio`, `_comments`, `_licensing`) until its step builds it. Their manifests validate, their routers declare access, and mypy, ESLint and `tsc` check them. Bodies raise NotImplementedError, models need their first migration, and the admin pages return null. **The leading `_` keeps the harness from mounting them** (folders starting with `_` are not modules, `harness/layout.py`): with no migrations, and with `comments` and `licensing` requiring modules not built yet, the harness's app would refuse to start and the migration check would fail. The step that builds a module renames it to `modules/<id>/` in the same PR as its first migration and tests, once every module it requires is in.

| Step | Session goal | Modules | Done when |
| --- | --- | --- | --- |
| 0 | Apply `kernel-additions.md` items 1 and 2 (K2's passkeys landed in #50) | kernel | `kernel.moderation.act` declared and seeded; custom roles count as staff |
| 1 | Lift the content modules | `media`, `pages`, `blog`, `embeds` (+ the YouTube playlist component), `contact`, `campaigns` | Each passes its brief's done-when |
| 2 | Build the homepage players | `discography`, `audio-player`, `featured` | Migrations up/down/up; upload makes a stream file and peaks; `/api/featured/slots/spotlight` serves live placements; Admin › Homepage › Players matches the canvas board |
| 3 | Complete the content side | `roster`, `portfolio`, `reactions`, `comments` | Artists edit only their own profile (require_owner_or test); guest comments wait for approval |
| 4 | Port the community | `community` | VybeMindz features on kernel auth and moderation; its tests ported |
| 5 | The marketplace core (DevKit v1.0 gate) | `payments`, `shop`, `downloads` | Stripe test-mode checkout end to end; the dashboard's Connect Stripe checklist goes green. **Site launch.** |
| 6 | The beat store | `licensing` | Tier table drafted for the owner (Q1); a test purchase issues a license PDF and `/license/<id>` checks it |
| 7 | The apparel designer | `print-on-demand` | Printful v2 re-checked; a test order reaches a Printful draft |

**Between step 0 and step 1** (decision 0029): K3, K4 with this site's theme (drafted in `C:\DEV\VM Website\design\theme\vibrant-mindz\`; its README says what K4 does with it), and K5, then decision 0018's ten hooks, so `devkit check` exists from step 1. K2's invites (its step 10) come before step 4, and its OAuth and deletion (steps 9 and 11) come before the launch at step 5.

**Site side** (the `VM Website` repo): after `devkit new`, copy in `site-additions/` (seed and the `/api/site/home` composer), then build the homepage from `design/site/Main.dc.html` into `web/src/site/`.

**Session prompt template:**

> Read AGENT-GUIDE.md, SPEC.md and docs/plans/vibrant-mindz-backend/KICKOFF.md. Do step N only. Work module by module; keep each module's manifest, MODULE.md and tests in step with the code. Stop when the step's done-when is met, update docs/HANDOFF.md, and list anything you had to decide.
