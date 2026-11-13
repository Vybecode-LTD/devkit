# AI DevKit

A library of reusable website modules that any AI agent can pick from and copy into a site's repo. Point an agent at this repo, describe the site in a few sentences, and it chooses the modules, copies them in and wires them together.

- **The contract:** [`SPEC.md`](SPEC.md)
- **For an agent building a site:** [`AGENT-GUIDE.md`](AGENT-GUIDE.md)
- **For an agent working on DevKit itself:** [`CLAUDE.md`](CLAUDE.md) / [`AGENTS.md`](AGENTS.md), then [`KICKOFF.md`](KICKOFF.md)

## How it works

1. **Kernel.** Every site gets the same core: auth, users and roles, settings, database, email, notifications, storage, events and jobs, moderation, audit, security and module switches.
2. **Modules.** Each feature is a folder with a manifest (`module.json`), a backend, a web front end, migrations and tests. Agents pick modules by the `use_when` and `avoid_when` lines in each manifest.
3. **Recipes.** Preset module lists for common kinds of site (a local business, an artist or band, a SaaS landing, a community, a shop, a publication).
4. **Copy-in.** `devkit add <module>` copies a module into a site and records it in the site's lock file. Sites own their copies; `devkit diff` and `devkit upgrade` bring later fixes across.

## Stack

FastAPI, Pydantic v2, async SQLAlchemy and Postgres on the backend; React 19, Vite and TypeScript on the front end; design tokens as CSS variables. See `SPEC.md` section 2.

## Status

Spec v0.1. The kernel is being built (`KICKOFF.md`): K0 and K1 are done, K2 (auth) is under way, and the audit of 2026-11-12 is fixed. The first site built on DevKit is the new Vibrant Mindz site. Decisions are in `docs/decisions/`.

## License

Proprietary, VybeCode Software. Selected modules may be released under MIT (decision 0008).
