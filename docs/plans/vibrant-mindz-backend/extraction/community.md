# community: port brief

- **How:** Port with the `mechframe-module-extractor` skill; lint with `module-contract-lint`.
- **Source:** VybeMindz `backend/app/routers/` (channels, messages, DMs, polls, bookmarks, uploads, roles, invites, moderation log).
- **On Vibrant Mindz:** Discord-style community for fans (Q3: open sign-up). Moves to kernel auth, sessions, moderation and notifications; theme tokens and the kernel UI kit; E2E DMs as a setting, off by default. Module plan section 8.
- **Rules to keep:** module layout and manifest per SPEC 4–5; tables `community_*`; permissions `community.<resource>.<action>`; no imports between modules except `public.py` / `web/public.ts` listed in `requires`; events for everything else (SPEC 11); admin screens on the kernel UI kit with the owner's lens (SPEC 8).
- **Done when:** `python -m tools.validate_schemas` is clean, the module's tests pass, `mechframe check` is green, and the admin page matches the canvas (https://claude.ai/artifact/W7EZQumtcK36K3xczG8mNH, Admin page) where one is drawn.
