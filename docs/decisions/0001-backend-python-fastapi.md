# 0001: Backend in Python with FastAPI

- **Date:** 2026-11-12
- **Status:** Locked
- **Context:** About 19 of the owner's backends are FastAPI, and VybeSite's kernel (the most hardened code in C:\DEV) is Python. The owner knows Python very well and TypeScript well.
- **Decision:** Python 3.12+, FastAPI, Pydantic v2 in strict mode, async SQLAlchemy 2 with asyncpg, Postgres 16+, Alembic. Front end: React 19, Vite, TypeScript strict. The typed client is generated with openapi-typescript and openapi-fetch (owner answers Q1 and Q2).
- **Alternatives:** An all-TypeScript backend (Hono or Node with Drizzle): one language and real server rendering, but every backend module would be rewritten, auth included.
- **Consequences:** Two languages per module and a generated client that must stay current; public pages need the server-copy pattern for crawlers (SPEC.md section 9). A TypeScript port is studied after v1.0 (decision 0004).
- **See:** SPEC.md section 2; the inventory (`docs/private/inventory.md`, not in git) section 5
