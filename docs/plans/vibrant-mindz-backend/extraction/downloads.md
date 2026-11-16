# downloads: build from plan brief

- **How:** Build from plan (new code, designed from the plan); lint with `module-contract-lint`.
- **Source:** VybeSite idea 4; CarbonDSP storefront (design only).
- **On Vibrant Mindz:** Entitlements, short-lived signed links into private storage, a Downloads page per customer, guest links by email. Exclusive videos and rap battle videos (Q2).
- **Rules to keep:** module layout and manifest per SPEC 4–5; tables `downloads_*`; permissions `downloads.<resource>.<action>`; no imports between modules except `public.py` / `web/public.ts` listed in `requires`; events for everything else (SPEC 11); admin screens on the kernel UI kit with the owner's lens (SPEC 8).
- **Done when:** `python -m tools.validate_schemas` is clean, the module's tests pass, `devkit check` is green, and the admin page matches the canvas (https://claude.ai/artifact/W7EZQumtcK36K3xczG8mNH, Admin page) where one is drawn.
