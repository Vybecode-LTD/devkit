# payments: build from plan brief

- **How:** Build from plan (new code, designed from the plan); lint with `module-contract-lint`.
- **Source:** VybeSite `dev plans/2026-10-11-product-ideas.md` idea 4; APMonster billing (design only).
- **On Vibrant Mindz:** Stripe Checkout first, PayPal next; keys sealed (SecretStr); signed webhooks; emits `payments.checkout.completed` and `payments.refund.issued`. Admin › Marketplace › Payments (the dashboard's "Connect Stripe").
- **Rules to keep:** module layout and manifest per SPEC 4–5; tables `payments_*`; permissions `payments.<resource>.<action>`; no imports between modules except `public.py` / `web/public.ts` listed in `requires`; events for everything else (SPEC 11); admin screens on the kernel UI kit with the owner's lens (SPEC 8).
- **Done when:** `python -m tools.validate_schemas` is clean, the module's tests pass, `mechframe check` is green, and the admin page matches the canvas (https://claude.ai/artifact/W7EZQumtcK36K3xczG8mNH, Admin page) where one is drawn.
