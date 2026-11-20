# Decisions

One short record per decision, numbered, written when the decision is made (`C:\DEV\DIRECTIVES.md`). A change to `SPEC.md` needs a record here and a line in its change log, in the same PR.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-backend-python-fastapi.md) | Backend in Python with FastAPI | Locked |
| [0002](0002-copy-in-modules.md) | Modules are copied into each site | Locked |
| [0003](0003-homemade-auth.md) | Homemade auth, owned by the kernel | Locked |
| [0004](0004-typescript-port-path.md) | Study a TypeScript port after v1.0 | Noted |
| [0005](0005-spec-first-validation.md) | Spec first, validated by three real modules | Locked |
| [0006](0006-vibrant-mindz-first-site.md) | The new Vibrant Mindz site is the first site | Locked |
| [0007](0007-kernel-notifications-moderation.md) | Kernel gains notifications and moderation | Applied |
| [0008](0008-repo-license-jobs-admin.md) | Repo, license, job queue and admin shell | Locked; the repo's visibility superseded by 0011, the admin shell's looks by 0040 |
| [0009](0009-k1-kernel-conventions.md) | Conventions settled while building the kernel's core (K1) | Applied; the module-switch read changed after the audit |
| [0010](0010-auth-http-contract.md) | The auth HTTP contract, and test support in the harness | Applied; its clock rule narrowed by 0013 |
| [0011](0011-public-repo.md) | The GitHub repo is public, for now | Applied; its CI claim corrected by 0015 |
| [0012](0012-keyed-one-time-secrets.md) | One-time secrets are kept as keyed hashes | Applied; amended 2026-11-14 |
| [0013](0013-auth-rules-from-the-audit.md) | Auth rules the audit found missing | Applied |
| [0014](0014-bounded-password-hashing.md) | Password hashing is bounded | Applied |
| [0015](0015-ci-gate-wiring.md) | How CI wires the quality gate | Applied |
| [0016](0016-spec-catches-up-with-the-code.md) | The spec catches up with the code | Applied |
| [0017](0017-retire-the-spec-doc.md) | Retire the claude.ai Spec doc | Applied |
| [0018](0018-module-roadmap-and-contract-hooks.md) | The module roadmap after v1.0, and the contract hooks it needs | Accepted; hooks not yet applied |
| [0019](0019-sign-in-limits-as-tiers.md) | Sign-in waits are rate-limit tiers, and second factors are limited per account | Applied |
| [0020](0020-sign-up-defaults.md) | Sign-up is closed until a site opens it, and its mail and links have limits | Applied |
| [0021](0021-codes-and-links.md) | An email code or link is one first factor, live once per account | Applied |
| [0022](0022-password-resets.md) | A reset ends every way in and marks the address verified | Applied |
| [0023](0023-verification-resend.md) | A signed-in account can ask for a new verification link | Applied |
| [0024](0024-email-change.md) | Email change is confirmed by the new address and undone by the old | Applied |
| [0025](0025-password-change.md) | A password change keeps its own session and gives way to a reset | Applied |
| [0026](0026-totp-setup-and-confirm.md) | A TOTP is set up, then confirmed by a code that can't be used again | Applied |
| [0027](0027-totp-removal-and-recovery-codes.md) | Removing a TOTP is a second-factor reset; new recovery codes need one | Applied |
| [0028](0028-passkeys.md) | Passkeys sign in alone or as a second factor; removing one is a second-factor reset | Applied |
| [0029](0029-vibrant-mindz-order.md) | The kernel's remaining work, in the order the Vibrant Mindz site needs it | Accepted |
| [0030](0030-second-factor-undo.md) | A passkey or TOTP someone else added is undone from its mail | Applied |
| [0031](0031-moderation-permission.md) | The kernel declares `kernel.moderation.act`, and a custom role is staff | Applied |
| [0032](0032-kernel-storage.md) | Kernel storage: two buckets, short signed links, downloads by default, and moto for the tests | Applied |
| [0033](0033-kernel-email.md) | Kernel email: templates a site can reword, and SMTP first, Resend only where SMTP is blocked | Applied |
| [0034](0034-rename-to-mechframe.md) | The project becomes MechFrame, after K3 | Accepted |
| [0035](0035-kernel-jobs.md) | Kernel jobs: a Postgres queue enqueued in the caller's transaction, at least once, with the worker in the web process by default | Applied |
| [0036](0036-kernel-events.md) | Kernel events: deliveries are jobs written at emit, so the jobs table is the outbox | Applied |
| [0037](0037-kernel-audit.md) | Kernel audit: one append-only log for every module, auth's widened | Applied |
| [0038](0038-kernel-notifications.md) | Kernel notifications: one template per key, each person's choice per key, and one-click unsubscribe | Applied |
| [0039](0039-kernel-moderation.md) | Kernel moderation: reports on declared kinds, one case per thing, filters that hold, bans as suspensions | Applied |
| [0040](0040-admin-shell-design.md) | The admin shell is built to the Vibrant Mindz canvas design, styled by tokens (amends 0008) | Decided; applied in K4 |
| [0041](0041-public-rendering.md) | Public rendering: one `page()` per address, matched by `routes.public`; the shell, `WEB_DIST` and the kernel's files | Applied |
| [0042](0042-web-kernel.md) | The web kernel: typed answers and a client from committed specs, kernel pages in one list, `--mf-*` tokens, the admin to the boards | Decided; applied in K4 |
| [0043](0043-sign-in-and-account-screens.md) | The sign-in and account screens: a frame of their own, the site's look in the kit, `GET /api/auth/security`, the device routes written down | Decided; applied in K4.5 |
| [0044](0044-admin-shell.md) | The admin shell: sections in the sidebar, "Needs you" for those who can act, the log naming its people, an info tone | Decided; applied in K4.6 |
| [0045](0045-people-and-roles.md) | People and roles in the admin: who may grant and edit what, the locks that keep the last owner, `auth.role.manage` | Decided; applied in K4.7 |
| [0046](0046-settings-features-system.md) | Settings, Features and System: the sign-up mode as a setting, switches that announce themselves, failed jobs that can only be discarded | Decided; applied in K4.8 |
| [0047](0047-cli-and-site-template.md) | The CLI and the site template: copied from the checkout, a site's exact layout, hashes that ignore line endings, what waits | Decided; applied in K5 from #91 |
| [0048](0048-site-pages-and-template.md) | The site's own pages, `kernel.load_module`, and how a site runs: always on, `backend` on the path, Railway as code | Decided; applied in K5.2 (#92) |
| [0049](0049-destructive-migrations-wait.md) | A destructive migration waits for the owner: named back with `--confirm-destructive`, once its branch holds data | Decided; applied in K5.3 (#93) |
| [0050](0050-add-and-remove.md) | `mechframe add` and `remove`: what each writes, what `remove` keeps, and how `requires` reads a range | Decided; applied in K5.4 (#94) |
