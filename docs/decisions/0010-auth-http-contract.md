# 0010: The auth HTTP contract, and test support in the harness

- **Date:** 2026-11-12
- **Status:** Applied; the clock rule narrowed by 0013
- **Context:** SPEC.md 14.13 asks for contract tests that call the HTTP API and import nothing of the kernel, so a TypeScript port can pass the same suite. Some cases need time to pass (a 30-minute token, a 14-day grace period), mail to read, an outside identity provider, or jobs to run.
- **Decision:**
  - The routes, bodies, status codes and problem codes the suite relies on are written down in `docs/contracts/auth-api.md`. That file is the contract; the suite in `kernel/tests/contract/` checks it.
  - The harness, never a site, mounts test-support routes at `/api/_test` when `HARNESS_TEST_SUPPORT=1`: reset, captured mail, a clock that moves forward, account seeding, a fake OAuth provider called `test`, running due jobs, and a probe module's record of delete hooks. A port's harness implements the same routes.
  - Every expiry and timeout in the kernel reads `kernel.clock.now()`, which only the test support moves. Rate-limit windows are the exception: they run on real time, and the test support resets them instead (narrowed by decision 0013).
  - Until the code for a contract test exists, the test is marked as an expected failure with `strict=True`, so it turns into a failure the moment it starts passing and its mark must be removed.
- **Alternatives:** Freezing time with a library inside the process (rejected: a port couldn't use it); seeding accounts through SQL (rejected: ties the suite to the schema).
- **Consequences:** Contract tests can run against any running server with `CONTRACT_BASE_URL`. The test-support routes are covered by a test that the plain harness app never mounts them.
- **See:** SPEC.md 14.13, `docs/contracts/auth-api.md`, `harness/testing.py`
