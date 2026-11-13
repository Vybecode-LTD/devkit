# Handoff

Overwritten every session. 2026-11-12, remote session (claude.ai in a cloud container, synced to `C:\DEV\AI-DevKit`).

## State

- **K0 and K1 done**, and **audited** (2026-11-12). The audit found 55 issues, none of them a leak; the report is private (`docs/private/`). It and the review bots' follow-ups landed as 24 pull requests, #1 to #24, each with its tests seen failing first and CI green.
- **K2 started:**
  1. The contract suite (`kernel/tests/contract/`) speaks HTTP only, against `docs/contracts/auth-api.md`. Each of its 83 tests is a strict expected failure that fails only with "not built", so it can't pass by accident or fail for the wrong reason.
  2. `kernel/auth/passwords.py` is done: a bounded Argon2id pool (503 `kernel.busy` when full), parameters from the config (`Passwords.from_config`), the rules, the bundled list and Pwned Passwords.
  3. Every auth table is in place (`kernel/auth/models.py`, migration `kernel_0002`, amended in place by the audit with an index on every foreign key). Its six permissions are declared in `kernel/kernel.json`.
  4. One-time secrets are kept as keyed hashes (`kernel/auth/hashing.py`, decision 0012).
  5. Test support: `reset` (with `{"accounts": true}`), `clock`, `routes`, `breached`.
- **Kernel changes from the audit:**
  - 500s keep their security headers, and request bodies have a limit (`MAX_BODY_BYTES`);
  - rate-limit keys can't collide, and each route has its own budget;
  - the module switches are cached per process for `MODULES_CACHE_SECONDS`;
  - settings keep typed secrets and work with strict models;
  - logs keep a traceback's end, scrub in linear time and write one access line per request;
  - the start-up checks are stricter (SECRET_KEY 43+ characters, an https SITE_URL outside DEBUG);
  - HSTS goes out behind a TLS edge.
- **Tests:** 271 Python tests pass with 83 strict expected failures, and coverage is 92% (CI fails under 85%). There are 7 web tests. The migration tests compare the full Postgres catalog, run a seeded round trip and a stairway, and include 11 mutant controls.
- **CI** runs on every PR, every push to `main`, weekly and by hand (decision 0015). Its first run was #1.
- **GitHub:** `https://github.com/Vybecode-LTD/devkit`, public (decision 0011). Commits use the owner's no-reply address. PRs land by fast-forwarding `main` to the PR's head once "CI result" is green; an API squash or rebase would stamp the token's address instead.
- **Common-password list:** NOTICE gives each source's own terms, and the tool's docstring has the exact rebuild.
- **Decisions:** 0012 to 0016 were added this session. SPEC 4 to 7, 14 (14.1 to 14.13 in places), 15 and 16 changed.

## Next

K2, in order: `dev plans\2026-11-12-next-session-k2-after-audit.md`.

## Questions for the owner

- **A ruleset for `main`:** require a PR and "CI result", and block force pushes. It's a repo setting, so it waits for your go-ahead.
- **Two commits carry the token's address:** #1's squash commit (`d935f0e`, as author) and #2's rebase (`b1a0190`, as committer). Rewriting them needs a force push to `main`. That's your call, and it should be done before a ruleset blocks force pushes.
- **Merged branches** are still on GitHub: the session couldn't delete them. Delete them in the UI or with `git push origin --delete <branch>`.
- **SHA-pinned actions with Dependabot** (decision 0015): yes or no?
- **The claude.ai Spec doc** needs SPEC 4 to 7, 14, 15, 16 and the change log synced (decisions 0012 to 0016).

## Notes

- **React Router stays on 7** (8 is out; moving needs a decision record). TypeScript stays on 6.0.x for typescript-eslint.
- **FastAPI 0.162** keeps included routers whole in `app.routes`: walk them with `fastapi.routing.iter_route_contexts`, as `kernel.ratelimit.route_name` does.
- **pytest runs with `--import-mode=importlib`.** Close any pool a test app opens: under coverage, an unclosed connection fails the next test.
- **gitleaks in CI** is the release binary checked against a pinned SHA-256. Bump both together.
- **The remote tools can't write `.npmrc` or `.github\`.** After a remote sync, run `git checkout -- .npmrc .github` before any `npm` command.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions (JWT for staff, cookies for members) and its split account tables differ from the spec. Port the behavior, not the shape.
