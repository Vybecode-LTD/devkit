# pages: lift brief

- **How:** Lift with the `devkit-module-extractor` skill; lint with `module-contract-lint`.
- **Source:** VybeSite `site_pages`, `site_theme.py`, `site_layout.py`, `fonts/catalogue.json`.
- **On Vibrant Mindz:** About, credits and other fixed pages. Admin › Content › Pages.
- **Rules to keep:** module layout and manifest per SPEC 4–5; tables `pages_*`; permissions `pages.<resource>.<action>`; no imports between modules except `public.py` / `web/public.ts` listed in `requires`; events for everything else (SPEC 11); admin screens on the kernel UI kit with the owner's lens (SPEC 8).
- **Done when:** `python -m tools.validate_schemas` is clean, the module's tests pass, `devkit check` is green, and the admin page matches the canvas (https://claude.ai/artifact/W7EZQumtcK36K3xczG8mNH, Admin page) where one is drawn.
