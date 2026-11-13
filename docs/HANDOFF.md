# Handoff

Overwritten every session. 2026-11-13: a remote session (claude.ai in a cloud container), then the first session in Claude Code on the owner's machine, which added sessions (#32).

## State

- **K0 and K1 done**, and **audited** (2026-11-12). The audit found 55 issues, none of them a leak; the report is private (`docs/private/`). It and the review bots' follow-ups landed as 24 pull requests, #1 to #24, each with its tests seen failing first and CI green.
- **K2 started:**
  1. The contract suite (`kernel/tests/contract/`) speaks HTTP only, against `docs/contracts/auth-api.md`. Each of its 83 tests is a strict expected failure that fails only with "not built", so it can't pass by accident or fail for the wrong reason.
  2. `kernel/auth/passwords.py` is done: a bounded Argon2id pool (503 `kernel.busy` when full), parameters from the config (`Passwords.from_config`), the rules, the bundled list and Pwned Passwords.
  3. Every auth table is in place (`kernel/auth/models.py`, migration `kernel_0002`, amended in place by the audit with an index on every foreign key). Its six permissions are declared in `kernel/kernel.json`.
  4. One-time secrets are kept as keyed hashes (`kernel/auth/hashing.py`, decision 0012).
  5. Test support: `reset` (with `{"accounts": true}`), `clock`, `routes`, `breached`.
  6. Sessions (`kernel/auth/sessions.py`, #32): opaque tokens kept as SHA-256, member and staff limits (`Lifetimes`), the session epoch, a new token after a role change and at step-up (one per race, #33), `last_seen_at` at most hourly (or every eighth of a shorter idle limit), the `__Host-` cookie helpers and the signed known-device cookie. 49 tests, 100% of the module.
- **Kernel changes from the audit:**
  - 500s keep their security headers, and request bodies have a limit (`MAX_BODY_BYTES`);
  - rate-limit keys can't collide, and each route has its own budget;
  - the module switches are cached per process for `MODULES_CACHE_SECONDS`;
  - settings keep typed secrets and work with strict models;
  - logs keep a traceback's end, scrub in linear time and write one access line per request;
  - the start-up checks are stricter (SECRET_KEY 43+ characters, an https SITE_URL outside DEBUG);
  - HSTS goes out behind a TLS edge.
- **Tests:** 320 Python tests pass on Linux CI (on Windows, 319 and a skipped symlink test) with 83 strict expected failures, and coverage is about 95% (CI fails under 85%). There are 7 web tests. The migration tests compare the full Postgres catalog, run a seeded round trip and a stairway, and include 11 mutant controls.
- **CI** runs on every PR, every push to `main`, weekly and by hand (decision 0015). Its first run was #1.
- **GitHub:** `https://github.com/Vybecode-LTD/devkit`, public (decision 0011). Commits use the owner's no-reply address. PRs land by fast-forwarding `main` to the PR's head once "CI result" is green; an API squash or rebase would stamp the token's address instead.
- **Common-password list:** NOTICE gives each source's own terms, and the tool's docstring has the exact rebuild.
- **Decisions:** 0012 to 0016 came from the audit, 0017 retired the Spec doc, and 0018 records the module roadmap after v1.0 and its ten contract hooks (none in SPEC.md yet). SPEC 4 to 7, 14 (14.1 to 14.13 in places), 15 and 16 changed in the audit.

## Next

K2, in order: `dev plans\2026-11-13-next-session-k2-in-claude-code.md`, from step 2 (the access dependencies); its set-up is done on the owner's machine. The suite should show 320 passed (Windows: 319 and 1 skipped) and 83 xfailed with Postgres up.

After K2 and the kernel phases, and before blog, chat and payments are extracted (SPEC 19, phase 3): the ten contract hooks of decision 0018, one PR per hook with `skills/devkit-hook-designer`. Start with export and erase, which the spec nearly has already (it needs an export contract test). The modules that follow v1.0 are in `docs/plans/module-roadmap.md`.

## The owner's answers (2026-11-13)

- **History rewritten:** `main` from #1 on was rewritten so no commit carries the API token's address. Trees, messages and dates are unchanged; everything before #1 keeps its hashes. **A clone made before 2026-11-13 must reset:** `git fetch origin`, then `git reset --hard origin/main` (with nothing of its own to keep).
- **Ruleset `main`:** on the default branch, it requires "CI result" to have passed on the exact commit (and the branch to be up to date for PR merges), and blocks force pushes and deletion (decision 0015). It has no "require a pull request" rule: that rule would force merges through GitHub's merge button, which stamps the API token's address on every merge. The check rule gives the same guarantee, since a commit only has a green "CI result" if it ran CI on a branch first.
- **Merged branches deleted;** finished PR branches are deleted after landing from now on.
- **Actions pinned** to commit SHAs, and Dependabot proposes the bumps weekly (#26).
- **The claude.ai Spec doc is retired** (decision 0017): titled "(retired)", with a notice that it's frozen as of 2026-11-12. `SPEC.md` is the only copy.

## Notes

- **Session lifetimes are a parameter** (`sessions.Lifetimes`, the spec's defaults). Reading them from the site's settings (Q6) comes with the dependencies, which also decide how `current_user` reads them without a query on every request.
- **A replaced token is dead at once** (14.5): a request still carrying it after a role change or a step-up gets 401. The web kernel's session hook (K4) should retry once on a 401 that follows a new cookie.
- **The device cookie is signed over the session epoch,** so a reset or a password change makes every browser a stranger. A route that raises the epoch on a browser that stays signed in (a password change) should set a fresh one.
- **React Router stays on 7** (8 is out; moving needs a decision record). TypeScript stays on 6.0.x for typescript-eslint.
- **FastAPI 0.162** keeps included routers whole in `app.routes`: walk them with `fastapi.routing.iter_route_contexts`, as `kernel.ratelimit.route_name` does.
- **pytest runs with `--import-mode=importlib`.** Close any pool a test app opens: under coverage, an unclosed connection fails the next test.
- **gitleaks in CI** is the release binary checked against a pinned SHA-256. Bump both together.
- **The remote tools can't write `.npmrc` or `.github\`.** After a remote sync, run `git checkout -- .npmrc .github` before any `npm` command.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions (JWT for staff, cookies for members) and its split account tables differ from the spec. Port the behavior, not the shape.
