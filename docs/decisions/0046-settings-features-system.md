# 0046: Settings, Features and System in the admin: the sign-up mode as a setting, switches that announce themselves, and failed jobs that can only be discarded

- **Date:** 2026-11-19
- **Status:** Decided; applied in K4.8 (#87)
- **Context:** K4.8 builds the admin's Settings to VM Website's `design/site/AdminSettings.dc.html` (K4 contract §2 additions 6 to 8, §4 item 8; decisions 0035, 0040 and 0042). The settings service, the module switches and the jobs queue were built in K1 and K3, but no route reached them. Building the routes found:
  - The contract's Site tab named "the auth section", but none existed: the kernel registered `kernel.site` and `kernel.moderation` only. Decision 0020 had said the site settings would take the sign-up mode over from `SIGN_UP_MODE` once their admin page landed.
  - A sealed job's contents are wiped when it fails for good (decision 0035), so a failed mail can't run again: its link is gone. A job whose name nothing declares any more has no handler.
  - SPEC 11 promised `kernel.module.enabled` and `kernel.module.disabled` "with the code that makes their change", and nothing emitted them; switches weren't audited either.
  - `on` alone can't say a module is switched on but waiting for one it needs: SPEC 12 keeps the dependent's own switch.
  - The harness installs no modules (the real ones wait as `modules/_<id>/` scaffolds), so the contract suite had nothing to switch and no job that fails.
- **Decision:**
  1. **`kernel.auth` holds `sign_up_mode`** (`open`, `invite` or `closed`), whose default is the deploy's `SIGN_UP_MODE`: until someone saves it, the variable stands; once saved, the setting wins. Sign-up reads it (the owner chose this over showing the variable read-only, 2026-11-19). The board's "Anyone can sign up" switch sets `open` or `closed`; `invite` shows as off until invites exist.
  2. **A failed job that can't run again can only be discarded** (the owner, over keeping sealed contents until the 30-day prune). The dead list says `retryable` for each; a retry of a sealed one or one nothing declares answers 409 `kernel.job_not_retryable`, as does a retry while another run of the same job and key waits (the live-key index refuses it). A retry gives the job its tries again, due now.
  3. **A switch announces itself.** One that changes something is audited as `kernel.module.enabled` or `kernel.module.disabled`, and emits that event for every module whose on-state changed, dependents included. Switches take one advisory lock; one to where it already is changes nothing. An unknown module answers 404 (it was 422).
  4. **The module list gains `switched` and `category`:** the admin's own switch beside the module's state, and the manifest's category, by which the page groups the modules as the board does.
  5. **The harness's probe modules** (`harness/probe.py`): `probe`, with a route, a settings section holding a secret, and two jobs, and `probe-addon`, which requires it, mounted by the test support only. `POST /api/_test/jobs` queues one of their jobs.
  6. **System reads the deploy, not the services' health:** the mail adapter (`smtp`, `resend` or `log`), whether storage and a public bucket are set, the kernel's version and how many modules are installed and on. The worker is `behind` only while a job it would take (its name declared, its module on) is more than 2 minutes late.
- **Alternatives:**
  - *Sign-up mode:* `SIGN_UP_MODE` shown read-only, the switch waiting; a setting that replaces the variable at once (a deploy's chosen mode lost on upgrade).
  - *Dead mail:* keep a dead sealed job's sealed contents until it's pruned, so it can be retried (a database dump holds those links for 30 days).
  - *Switch events:* one event for the module switched only (a listener misses its own module going off with another).
- **Consequences:**
  - Once an admin saves the sign-up mode, changing `SIGN_UP_MODE` on the host does nothing until the setting is saved again. Tests that rely on the variable clear any saved mode first.
  - The Site tab has one Save, the board's, in the page header; the kit's save bar isn't used there, so the page never shows two.
  - `auth.user.role_changed`, also promised by SPEC 11 for K4's admin, is still not emitted: K4.7 audits grants as `auth.user.roles_changed` but emits nothing.
- **See:** `dev plans/contracts/k4-web-kernel.md`, change 19; SPEC 11, 12 and 14.7; decisions 0020, 0035 and 0042; `kernel/backend/kernel/admin.py`
