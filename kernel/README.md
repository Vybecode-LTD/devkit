# Kernel

The always-installed core every module depends on (SPEC.md sections 6 and 14). Built in phases K1 to K4 of `KICKOFF.md`, lifted mostly from VybeSite.

| Folder | Holds |
| --- | --- |
| `backend/kernel/` | The Python package. Its `__init__.py` is the public surface modules may import; everything else is private |
| `migrations/` | Alembic branch `kernel`; every module's branch depends on it |
| `web/` | App shell, session hooks, generated API client, `defineModule`, slots and the UI kit. `web/index.ts` is the public surface |
| `tests/` | Kernel tests, including the auth contract tests (SPEC.md 14.13) in `tests/contract/` |
