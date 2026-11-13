"""Builds a site's app from the kernel and its modules (SPEC.md sections 6 and 12).

Lifted from VybeSite `main.py`. A site's `backend/app/main.py` is:

    from kernel import create_app
    from app.modules import INSTALLED   # written by `devkit add`

    app = create_app(modules=INSTALLED)

What it does, in order:
1. Reads the config and refuses to start on unsafe secrets (outside DEBUG).
2. Sets up logging and, when SENTRY_DSN is set, error tracking.
3. Checks MODULES against the installed modules and their requirements.
4. Mounts the kernel's routes at /api/kernel and each module's router at
   /api/<id>, behind `require_module(id)`.
5. Adds the middleware: SecurityHeaders (outermost), WwwRedirect, CORS (when
   CORS_ORIGINS is set), SameOriginWrites, BodyLimit, SessionCookies (a
   replaced session token reaches the browser on any answer, errors too) and
   UnexpectedErrors (innermost, so even a 500 carries the security headers).
6. Answers every error as problem details.

The API docs (/docs, /redoc, /openapi.json) are served only with DEBUG on: on
a live site they would map every route for anyone.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from kernel import error_tracking, logs
from kernel.auth.dependencies import SessionCookies
from kernel.config import KernelConfig, get_config, modules_allowed, refuse_unsafe
from kernel.db import Database
from kernel.errors import BodyLimit, UnexpectedErrors, install_handlers
from kernel.logs import AccessLog
from kernel.modules import InstalledModule, ModuleRegistry, require_module
from kernel.ratelimit import RateLimiter
from kernel.routes import router as kernel_router
from kernel.security import ContentSecurityPolicy, SameOriginWrites, SecurityHeaders, WwwRedirect
from kernel.settings import settings
from kernel.version import __version__

log = logging.getLogger(__name__)


def create_app(
    *,
    modules: Iterable[InstalledModule] = (),
    config: KernelConfig | None = None,
    database: Database | None = None,
) -> FastAPI:
    config = config or get_config()
    refuse_unsafe(config)
    logs.configure(config.log_format, config.log_level)
    error_tracking.init(config, "web")

    installed = list(modules)
    try:
        allowed = modules_allowed(config, {module.id for module in installed})
        registry = ModuleRegistry(installed, allowed, ttl=config.modules_cache_seconds)
    except ValueError as error:
        raise RuntimeError(f"Refusing to start: {error}") from error

    policy = ContentSecurityPolicy()
    for module in installed:
        for directive, source in module.csp:
            policy.allow(directive, source, module=module.id)
        if module.settings is not None:
            settings.register(module.id, module.settings)

    owns_database = database is None
    db = database or Database(
        config.database_url,
        pool_size=config.db_pool_size,
        max_overflow=config.db_max_overflow,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            async with db.sessions() as session:
                await registry.on(session)
        except (SQLAlchemyError, OSError) as error:
            log.warning(
                "Couldn't read which modules are switched off (%s); taking every module "
                "MODULES allows as on until the database answers.",
                type(error).__name__,
            )
        yield
        if owns_database:
            await db.dispose()

    docs = {} if config.debug else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title=config.site_name, version=__version__, lifespan=lifespan, **docs)  # type: ignore[arg-type]
    app.state.config = config
    app.state.database = db
    app.state.modules = registry
    app.state.csp = policy
    app.state.limiter = RateLimiter(config.rate_limit_storage, enabled=config.rate_limit_enabled)
    app.state.client_ip_header = config.client_ip_header
    install_handlers(app)

    app.include_router(kernel_router, prefix="/api/kernel")
    for module in installed:
        if module.router is not None:
            app.include_router(
                module.router,
                prefix=f"/api/{module.id}",
                dependencies=[Depends(require_module(module.id))],
            )

    # Starlette runs the last added outermost.
    app.add_middleware(UnexpectedErrors)
    app.add_middleware(SessionCookies)
    app.add_middleware(BodyLimit, max_bytes=config.max_body_bytes)
    origins = [config.site_url] + (config.cors_origins_list if config.debug else [])
    app.add_middleware(SameOriginWrites, origins=origins)
    if config.cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origins_list,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(WwwRedirect, site_url=config.site_url)
    app.add_middleware(
        SecurityHeaders,
        policy=policy,
        modules_on=registry.on_cached,
        refresh=lambda: registry.current(db.sessions),
        hsts_max_age=config.hsts_max_age,
        noindex=config.robots_noindex,
        https_site=config.site_url.strip().lower().startswith("https://"),
    )
    app.add_middleware(AccessLog)  # outermost: the whole request, the final status
    return app
