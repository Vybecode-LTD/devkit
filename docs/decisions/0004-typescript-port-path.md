# 0004: Study a TypeScript port after v1.0

- **Date:** 2026-11-12
- **Status:** Noted
- **Context:** The owner asked to keep a later move of the backend to TypeScript possible and to look for ways to reduce its cost after v1.
- **Decision:** v1 keeps every contract language-neutral: committed openapi.json, HTTP-level contract tests, RFC 9457 errors, JSON Schema for events and settings, standard credential formats, and a schema.sql export per release. After v1.0, one module is ported against the same contract tests and the result is decided in a new record.
- **Alternatives:** Porting now (rejected: rewrites the hardened kernel); never porting (rejected: the owner wants the option).
- **Consequences:** Every module's tests include contract tests that don't import its Python.
- **See:** SPEC.md section 19
