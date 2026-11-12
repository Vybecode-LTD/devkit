# 0002: Modules are copied into each site

- **Date:** 2026-11-12
- **Status:** Locked
- **Context:** DevKit exists so the owner and AI agents can build sites faster. It is not meant to be a WordPress-style system with runtime plugins.
- **Decision:** Modules are copied into a site's repo by `devkit add`, never installed as packages. The site's `devkit.lock.json` records versions and file hashes.
- **Alternatives:** Versioned packages (npm and pip): automatic updates, but harder for agents to customize and a heavier release process.
- **Consequences:** Fixes don't reach sites on their own, so security fixes travel as advisories that `devkit check` flags (SPEC.md section 13), and `devkit diff` / `upgrade` carry changes across.
- **See:** SPEC.md sections 12 and 13
