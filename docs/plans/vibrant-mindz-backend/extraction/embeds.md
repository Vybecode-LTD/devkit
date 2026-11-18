# embeds: lift brief

- **How:** Lift with the `mechframe-module-extractor` skill; lint with `module-contract-lint`.
- **Source:** VybeSite `services/embeds.json`, `MediaEmbed.tsx`, contract `dev plans/contracts/media-embeds.md`.
- **On Vibrant Mindz:** YouTube, SoundCloud, Spotify and Bandcamp from a pasted link. **Add for Vibrant Mindz:** the YouTube playlist player as a `web/public.ts` component (spec `videos-player.md`): facade first, IFrame API, autoplay through the list, one-thing-plays-at-a-time through `audio-player`'s store.
- **Rules to keep:** module layout and manifest per SPEC 4–5; tables `embeds_*`; permissions `embeds.<resource>.<action>`; no imports between modules except `public.py` / `web/public.ts` listed in `requires`; events for everything else (SPEC 11); admin screens on the kernel UI kit with the owner's lens (SPEC 8).
- **Done when:** `python -m tools.validate_schemas` is clean, the module's tests pass, `mechframe check` is green, and the admin page matches the canvas (https://claude.ai/artifact/W7EZQumtcK36K3xczG8mNH, Admin page) where one is drawn.
