# media: lift brief

- **How:** Lift with the `mechframe-module-extractor` skill; lint with `module-contract-lint`.
- **Source:** VybeSite `media_service.py` (Pillow re-encode, metadata strip), `ImagePicker.tsx`, `EmbedPicker.tsx`; Basefra.me `storage/` and its R2 CDN worker.
- **On Vibrant Mindz:** The media library every module picks images from: covers, member photos, artwork, product shots. `blog` requires it; the `artist-or-band` recipe lists it.
- **Rules to keep:** module layout and manifest per SPEC 4–5; tables `media_*`; permissions `media.<resource>.<action>`; no imports between modules except `public.py` / `web/public.ts` listed in `requires`; events for everything else (SPEC 11); admin screens on the kernel UI kit with the owner's lens (SPEC 8).
- **Done when:** `python -m tools.validate_schemas` is clean, the module's tests pass, `mechframe check` is green, and the admin page matches the canvas (https://claude.ai/artifact/W7EZQumtcK36K3xczG8mNH, Admin page) where one is drawn.
