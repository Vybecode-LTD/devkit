# Proposal: npm audit with an expiring allowlist (adopted)

**Adopted on 2026-11-17 by the owner (#75, decision 0015):** the three files moved to `tools/npm_audit.py`, `tools/npm_audit_allow.json` and `tests/test_npm_audit.py`, and CI runs `python3 -m tools.npm_audit`. What follows is the proposal as it was parked.

## Why

On 2026-11-17 (updated 15:56 UTC) GitHub widened advisory GHSA-fc5q-39xc-vjpf, a ReDoS in picomatch, to every version up to 4.0.7, the latest. No fixed version exists. picomatch reaches only the build and test tools (vite, vitest, typescript-eslint); `npm ls picomatch --omit=dev` lists nothing, and an attack needs an attacker-written glob pattern. CI's `npm audit --audit-level=low` fails on it, so every push to `main` from 19:09 UTC (#69's head) on has failed its Web job; npm audit still passed at 17:13 UTC, when that run failed instead on a flaky test (`test_each_request_gets_one_redacted_access_line`, fixed in #73). A pull request's run skips the Web job unless it touches web paths, which is why the pull requests themselves stayed green.

npm can't accept an advisory, and no upgrade fixes this one.

## What's here

- `npm_audit.py.txt`, meant for `tools/npm_audit.py`: runs `npm audit --json` and fails on any advisory not on the list, on an entry past its `until` date or more than 90 days out, and on an entry npm no longer reports, so the list can't outlive its reasons.
- `npm_audit_allow.json`, meant for `tools/`: the one entry, picomatch, until 2026-12-17, with its reason.
- `test_npm_audit.py.txt`, meant for `tests/test_npm_audit.py`: 15 tests, all passing on 2026-11-17. Run locally, the tool reported only the allowed advisory and exited 0.

## To adopt it (with the owner's OK)

1. Move the three files to `tools/` and `tests/`, dropping the `.txt` (it keeps ruff and pytest off them while they're parked).
2. In `.github/workflows/ci.yml`, replace `npm audit --audit-level=low` with `python3 -m tools.npm_audit`.
3. Amend decision 0015 with a line, and add the command to the Commands table in `CLAUDE.md` and `AGENTS.md`.

The alternatives: leave `main`'s push runs red until picomatch ships a fix, or wait and see whether vite and vitest drop picomatch.
