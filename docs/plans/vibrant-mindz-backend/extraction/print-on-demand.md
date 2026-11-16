# print-on-demand: build from plan brief

- **How:** Build from plan (new code, designed from the plan); lint with `module-contract-lint`.
- **Source:** VybeSite idea 5 and its research; skill `printful-v2-adapter`.
- **On Vibrant Mindz:** Printful v2 adapter, cached catalog, print-file renderer, the apparel designer (react-konva). Last step. Re-check Printful v2 (beta) before building.
- **Rules to keep:** module layout and manifest per SPEC 4–5; tables `print_on_demand_*`; permissions `print-on-demand.<resource>.<action>`; no imports between modules except `public.py` / `web/public.ts` listed in `requires`; events for everything else (SPEC 11); admin screens on the kernel UI kit with the owner's lens (SPEC 8).
- **Done when:** `python -m tools.validate_schemas` is clean, the module's tests pass, `devkit check` is green, and the admin page matches the canvas (https://claude.ai/artifact/W7EZQumtcK36K3xczG8mNH, Admin page) where one is drawn.
