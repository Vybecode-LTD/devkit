# shop: build from plan brief

- **How:** Build from plan (new code, designed from the plan); lint with `module-contract-lint`.
- **Source:** VybeSite idea 4.
- **On Vibrant Mindz:** Products with variants and stock (a painting has 1), shipping rates, cart, orders, receipts. The marketplace's CDs, vinyl, paintings, poetry books and (with `downloads`) exclusive videos and rap battles. Admin › Marketplace › Products and Orders (canvas board "Admin: Marketplace products").
- **Rules to keep:** module layout and manifest per SPEC 4–5; tables `shop_*`; permissions `shop.<resource>.<action>`; no imports between modules except `public.py` / `web/public.ts` listed in `requires`; events for everything else (SPEC 11); admin screens on the kernel UI kit with the owner's lens (SPEC 8).
- **Done when:** `python -m tools.validate_schemas` is clean, the module's tests pass, `devkit check` is green, and the admin page matches the canvas (https://claude.ai/artifact/W7EZQumtcK36K3xczG8mNH, Admin page) where one is drawn.
