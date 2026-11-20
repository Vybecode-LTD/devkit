# dev plans

Session prompts and working plans, the owner's convention across `C:\DEV`. Each session ends with a starting prompt for the next one saved here as `<date>-next-session-<topic>.md`. When a prompt's session is done, it moves to `done/`, so the one left here is the job. Durable decisions go in `docs/decisions/`, not here.

`progress-ledger/` is the source of the visual progress ledger, https://claude.ai/artifact/48auLkb7Ajmyn2SNAni9rm: its page (`index.html`) and the rows `python -m tools.progress` makes from `docs/progress.json` (`rows.json`); its README says how to republish it.

`2026-11-17-k3-gate-evidence.md` is the evidence K3's gate was checked on: each service's tests and coverage, the two named tests, and the kernel's contract lint (#75).

`2026-11-19-k45-screens/` holds the sign-in and account screens beside their boards, at 1440 and 390 px in both themes, with what differs and why (#83).

`2026-11-19-k46-admin/` holds the admin's Dashboard and Activity beside their boards (and the boards as drawn), at 1440 and 390 px in both themes, with what differs and why (#84).

`2026-11-19-k47-people-roles/` holds the admin's People and Roles beside their boards (and the boards as drawn), at 1440 and 390 px in both themes, with both dialogs, and what differs and why (#85).

`2026-11-19-k48-settings-system/` holds the admin's Settings tabs (Site, Features, System) at 1440 and 390 px in both themes, with failed jobs on System, and `README.md` saying what differs from `AdminSettings.dc.html` and why (#87).

`2026-11-20-k4-gate-evidence.md` is the evidence K4's gate was checked on (contract §7): the runs, each bullet's tests, the one finding (a stale People list after a save under load, fixed by #89), and the kernel's contract lint (#90).

`contracts/` holds the one-page contract each feature that touches a seam gets before its code (`C:\DEV\knowledge\decisions\0008-feature-contracts.md`):

| File | What |
| --- | --- |
| `contracts/k3-storage.md` | K3's storage service, `kernel.storage` (PR #58) |
| `contracts/k3-email.md` | K3's email service: `email.send`, templates, SMTP and Resend (PR #59) |
| `contracts/kernel-auth-templates.md` | K2's auth mails on `kernel.*` templates (PR #60) |
| `contracts/k3-jobs.md` | K3's jobs: the queue, the worker and the scheduler, `kernel.jobs` (PR #63) |
| `contracts/k3-events.md` | K3's events: `events.emit`, listeners delivered as jobs, dead letters, `kernel.events` (PR #65) |
| `contracts/k3-audit.md` | K3's audit log: `audit.record` for every module, the staff and own-activity reads, pruning, `kernel.audit` (PR #67) |
| `contracts/k3-notifications.md` | K3's notifications: `notifications.notify`, per-person preferences per key, one-click unsubscribe, `kernel.notifications` (PR #69 predicted) |
| `contracts/k3-moderation.md` | K3's moderation: reports, the staff queue, word and link filters, actions and suspension, `kernel.moderation` (PR #71) |
| `contracts/k3-public-rendering.md` | K3's public rendering: each page's head, words and JSON-LD in the shell, real 404s, `sitemap.xml`, `robots.txt`, `llms.txt`, `kernel.server_copy` (PR #73) |
| `contracts/k4-web-kernel.md` | K4's web kernel: the typed client, the app shell, session, guards, slots, themes, the UI kit, the auth and account screens and the admin shell (with role editing and System), in eight PRs from #78 |

`npm-audit-allowlist/`: the proposal for `npm audit` with an expiring allowlist, adopted 2026-11-17 (#75, decision 0015). The tool, its list and its tests now live in `tools/` and `tests/`; the README stays as the record of why.
