# 0008: Repo, license, job queue and admin shell

- **Date:** 2026-11-12
- **Status:** Locked
- **Context:** Owner answers Q3, Q8, Q9 and Q11.
- **Decision:** Repo at C:\DEV\AI-DevKit with a private GitHub repo Vybecode-LTD/devkit (created only after the owner says so). DevKit is proprietary; selected modules may be released under MIT. Background jobs run on a Postgres-backed queue, so no extra service. The admin shell is VybeSite's, as it stands.
- **Alternatives:** Redis with arq for jobs; a fresh admin shell.
- **Consequences:** Redis is added only for realtime pub/sub once a site runs more than one worker.
- **See:** SPEC.md sections 2 and 20
