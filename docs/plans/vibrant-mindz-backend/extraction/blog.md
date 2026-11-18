# blog: lift brief

- **How:** Lift with the `mechframe-module-extractor` skill; lint with `module-contract-lint`.
- **Source:** VybeSite `blog_admin`, `blog_public`, `writing_styles`, `writing_constitution`, `FormatToolbar.tsx`, `MarkdownEmbed.tsx`.
- **On Vibrant Mindz:** News, poetry posts and rap battle write-ups. Uses `comments` under posts once it exists.
- **Rules to keep:** module layout and manifest per SPEC 4–5; tables `blog_*`; permissions `blog.<resource>.<action>`; no imports between modules except `public.py` / `web/public.ts` listed in `requires`; events for everything else (SPEC 11); admin screens on the kernel UI kit with the owner's lens (SPEC 8).
- **Done when:** `python -m tools.validate_schemas` is clean, the module's tests pass, `mechframe check` is green, and the admin page matches the canvas (https://claude.ai/artifact/W7EZQumtcK36K3xczG8mNH, Admin page) where one is drawn.
