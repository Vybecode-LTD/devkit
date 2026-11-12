# 0007: Kernel gains notifications and moderation

- **Date:** 2026-11-12
- **Status:** Applied
- **Context:** Comments, community, orders and licenses all need notices; comments, community and any future forum need moderation. Modules may not import each other.
- **Decision:** The kernel adds `notify` and `moderation`. Modules may share UI through `web/public.ts` when listed in `requires.modules`. Object storage keeps private files behind signed links and gives provider-fetched files public, unguessable, expiring links. Each embed provider and payment host joins the CSP only while switched on. The manifest gains `notifications`. Python packages and table prefixes use the id with hyphens turned into underscores.
- **Alternatives:** A notifications module and a moderation module (rejected: nearly every module would require them).
- **Consequences:** The kernel grows; both are built in phase K3.
- **See:** SPEC.md sections 6, 7, 15 and the change log
