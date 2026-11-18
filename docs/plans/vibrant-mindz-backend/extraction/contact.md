# contact: lift brief

- **How:** Lift with the `mechframe-module-extractor` skill; lint with `module-contract-lint`.
- **Source:** VybeSite `contact_form`, `contact_service`, `contact_filter`, `contact_alerts`.
- **On Vibrant Mindz:** Contact and booking inquiries. Admin › Content › Inbox.
- **Rules to keep:** module layout and manifest per SPEC 4–5; tables `contact_*`; permissions `contact.<resource>.<action>`; no imports between modules except `public.py` / `web/public.ts` listed in `requires`; events for everything else (SPEC 11); admin screens on the kernel UI kit with the owner's lens (SPEC 8).
- **Done when:** `python -m tools.validate_schemas` is clean, the module's tests pass, `mechframe check` is green, and the admin page matches the canvas (https://claude.ai/artifact/W7EZQumtcK36K3xczG8mNH, Admin page) where one is drawn.
