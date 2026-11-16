# reactions: port brief

- **How:** Port with the `devkit-module-extractor` skill; lint with `module-contract-lint`.
- **Source:** VybeMindz reactions and custom emojis.
- **On Vibrant Mindz:** Shared by `community` and `comments`. Small; port first in that step.
- **Rules to keep:** module layout and manifest per SPEC 4–5; tables `reactions_*`; permissions `reactions.<resource>.<action>`; no imports between modules except `public.py` / `web/public.ts` listed in `requires`; events for everything else (SPEC 11); admin screens on the kernel UI kit with the owner's lens (SPEC 8).
- **Done when:** `python -m tools.validate_schemas` is clean, the module's tests pass, `devkit check` is green, and the admin page matches the canvas (https://claude.ai/artifact/W7EZQumtcK36K3xczG8mNH, Admin page) where one is drawn.
