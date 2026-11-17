"""Builds a site's app from the kernel and its modules (SPEC.md sections 6 and 12).

Lifted from VybeSite `main.py`. A site's `backend/app/main.py` is:

    from kernel import create_app
    from app.modules import INSTALLED   # written by `devkit add`

    app = create_app(modules=INSTALLED)

What it does, in order:
1. Reads the config and refuses to start on unsafe secrets (outside DEBUG).
2. Sets up logging and, when SENTRY_DSN is set, error tracking.
3. Checks MODULES against the installed modules and their requirements.
4. Mounts the kernel's routes at /api/kernel, auth's at /api/auth, and each
   module's router at /api/<id>, behind `require_module(id)`.
5. Adds the middleware: SecurityHeaders (outermost), WwwRedirect, CORS (when
   CORS_ORIGINS is set), SameOriginWrites, BodyLimit, SessionCookies (a
   replaced session token reaches the browser on any answer, errors too) and
   UnexpectedErrors (innermost, so even a 500 carries the security headers).
6. Answers every error as problem details.
7. Installs the mailer (`mailer=`, else SMTP when SMTP_HOST is set, else
   Resend when only RESEND_API_KEY is, else `LogMailer`, which sends nothing)
   behind `kernel.email.Checked`, as
   `app.state.mailer`, and the breach lookup new passwords are checked against
   (`breach_lookup=`, else Have I Been Pwned's range API), as
   `app.state.breach_lookup`.
8. Checks the kernel's own email templates (`kernel.auth.mails`), every
   module's, and the site's rewording of them
   (`emails=`), refusing to start on a bad one, and installs them with the
   mailer for `kernel.email.send`.
9. Checks the kernel's events and every module's (`kernel.events.build`)
   and installs them for `kernel.events.emit` (decision 0036); installs the
   modules that may write to the audit log, and how long it's kept
   (`kernel.audit.install`, decision 0037); checks each module's notification
   keys against its templates and installs them, the kernel's own first
   (`kernel.notifications`, decision 0038); checks what each module lets
   people report and installs it, with the filters' settings section
   (`kernel.moderation`, decision 0039); checks the
   kernel's jobs and every module's, their listeners' deliveries among them
   (`kernel.jobs.build`), and builds the site's worker as `app.state.worker`.
   With JOBS_IN_WEB on (the default) the lifespan runs it in this process; a
   site that runs `kernel.worker.serve` as a service of its own turns it off
   (decision 0035).
10. Checks every module's public and member pages (`kernel.server_copy`:
    `routes.public` and `pages` together, no two patterns answering one
    address at one rank) and the shell (`WEB_DIST`, refused without its
    markers), registers the settings section `kernel.site`, and registers,
    after every other route, the kernel's files (`/sitemap.xml`,
    `/robots.txt`, `/llms.txt`) and the catch-all that answers every address
    outside the API (`kernel.shell`, decision 0041); HEAD is answered as GET.

Steps 1 to 3, 7 and 8, the events' and jobs' checks and registering each
module's settings model, and checking the pages, are `assemble`, which
`kernel.worker.create_worker` shares, so a worker process starts on exactly
what the web app would.

The API docs (/docs, /redoc, /openapi.json) are served only with DEBUG on: on
a live site they would map every route for anyone.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from kernel import (
    audit,
    email,
    error_tracking,
    events,
    jobs,
    logs,
    moderation,
    notifications,
    server_copy,
    shell,
)
from kernel.auth.codes import router as codes_router
from kernel.auth.dependencies import SessionCookies
from kernel.auth.email_change import router as email_change_router
from kernel.auth.factor_undo import router as factor_undo_router
from kernel.auth.mails import TEMPLATES as KERNEL_MAILS
from kernel.auth.passkeys import router as passkeys_router
from kernel.auth.password_change import router as password_change_router
from kernel.auth.passwords import Passwords, RangeLookup, ask_range
from kernel.auth.permissions import KERNEL_PERMISSIONS
from kernel.auth.resets import router as resets_router
from kernel.auth.routes import router as auth_router
from kernel.auth.sign_up import router as sign_up_router
from kernel.auth.totp import router as totp_router
from kernel.auth.unverified import REMOVE as REMOVE_UNVERIFIED
from kernel.config import KernelConfig, get_config, modules_allowed, refuse_unsafe
from kernel.db import Database
from kernel.email import Checked, Mailer, Template, build_templates
from kernel.errors import BodyLimit, UnexpectedErrors, install_handlers
from kernel.logs import AccessLog
from kernel.mail_adapters import mailer_from_config
from kernel.modules import InstalledModule, ModuleRegistry, require_module
from kernel.ratelimit import RateLimiter
from kernel.routes import router as kernel_router
from kernel.security import ContentSecurityPolicy, SameOriginWrites, SecurityHeaders, WwwRedirect
from kernel.settings import settings
from kernel.version import __version__
from kernel.worker import Worker

log = logging.getLogger(__name__)

#: The kernel's own jobs: queued mail, pruning the queue, removing accounts
#: whose address isn't verified (decision 0035), and pruning the audit log
#: (decision 0037), the notices (decision 0038) and closed moderation cases
#: (decision 0039).
KERNEL_JOBS: tuple[jobs.Job, ...] = (
    email.SEND_MAIL,
    jobs.PRUNE,
    REMOVE_UNVERIFIED,
    audit.PRUNE,
    notifications.PRUNE,
    moderation.PRUNE,
)


@dataclass(frozen=True)
class Assembled:
    """What the web app and a worker process are both built from."""

    config: KernelConfig
    installed: tuple[InstalledModule, ...]
    registry: ModuleRegistry
    mailer: Checked
    jobs: tuple[jobs.Job, ...]
    #: The modules' public and member pages (kernel.server_copy).
    public: server_copy.Routes

    def database(self) -> Database:
        return Database(
            self.config.database_url,
            pool_size=self.config.db_pool_size,
            max_overflow=self.config.db_max_overflow,
        )


def assemble(
    *,
    modules: Iterable[InstalledModule] = (),
    config: KernelConfig | None = None,
    mailer: Mailer | None = None,
    emails: Mapping[str, Template] | None = None,
    role: Literal["web", "worker"] = "web",
) -> Assembled:
    """Reads and checks the config, the modules, their mail templates, events
    and jobs, and installs the mailer and templates for `kernel.email` and the
    events for `kernel.events`.
    Raises RuntimeError("Refusing to start: ...") on anything it can't take."""
    config = config or get_config()
    refuse_unsafe(config)
    logs.configure(config.log_format, config.log_level)
    error_tracking.init(config, role)

    installed = tuple(modules)
    try:
        allowed = modules_allowed(config, {module.id for module in installed})
        registry = ModuleRegistry(installed, allowed, ttl=config.modules_cache_seconds)
    except ValueError as error:
        raise RuntimeError(f"Refusing to start: {error}") from error
    try:
        templates = build_templates(
            [
                ("kernel", {**KERNEL_MAILS, **notifications.TEMPLATES, **moderation.TEMPLATES}),
                *((module.id, module.emails) for module in installed),
            ],
            emails or {},
        )
        kinds = notifications.build(
            [
                ("kernel", moderation.NOTIFICATIONS),
                *(
                    (module.id, module.manifest.raw.get("notifications") or [])
                    for module in installed
                ),
            ],
            templates,
        )
        reportable = moderation.build((module.id, module.reportable) for module in installed)
        public = server_copy.build(installed)
        catalog = events.build(
            [
                ("kernel", events.KERNEL_PAYLOADS, (), None),
                *(
                    (
                        module.id,
                        module.payloads,
                        module.listeners,
                        module.manifest.raw.get("events") or {},
                    )
                    for module in installed
                ),
            ],
            allowed=registry.allowed,
        )
        declared = jobs.build(
            [
                ("kernel", KERNEL_JOBS, None),
                *(
                    (
                        module.id,
                        (*module.jobs, *(listener.job for listener in module.listeners)),
                        module.manifest.raw.get("jobs") or [],
                    )
                    for module in installed
                ),
            ]
        )
    except ValueError as error:
        raise RuntimeError(f"Refusing to start: {error}") from error
    checked = Checked(mailer if mailer is not None else mailer_from_config(config))
    email.install(checked, templates, site_name=config.site_name, site_url=config.site_url)
    events.install(catalog)
    audit.install((module.id for module in installed), keep_days=config.audit_keep_days)
    notifications.install(kinds)
    moderation.install(reportable)
    server_copy.install(site_name=config.site_name, site_url=config.site_url)
    # Here, not in create_app: a job in a worker of its own reads its module's
    # settings too (Codex on #63).
    settings.register(moderation.SECTION, moderation.Filters)
    settings.register(server_copy.SECTION, server_copy.SiteSettings)
    for module in installed:
        if module.settings is not None:
            settings.register(module.id, module.settings)
    return Assembled(config, installed, registry, checked, declared, public)


def create_app(
    *,
    modules: Iterable[InstalledModule] = (),
    config: KernelConfig | None = None,
    database: Database | None = None,
    mailer: Mailer | None = None,
    breach_lookup: RangeLookup | None = None,
    emails: Mapping[str, Template] | None = None,
) -> FastAPI:
    built = assemble(modules=modules, config=config, mailer=mailer, emails=emails, role="web")
    config, installed, registry = built.config, built.installed, built.registry
    try:
        app_shell = shell.Shell.load(config.web_dist)
    except ValueError as error:
        raise RuntimeError(f"Refusing to start: {error}") from error

    policy = ContentSecurityPolicy()
    for module in installed:
        for directive, source in module.csp:
            policy.allow(directive, source, module=module.id)

    owns_database = database is None
    db = database or built.database()
    worker = Worker(
        built.jobs,
        registry=registry,
        database=db,
        mailer=built.mailer,
        concurrency=config.jobs_concurrency,
        poll=config.jobs_poll_seconds,
        drain=config.jobs_drain_seconds,
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
        stop = asyncio.Event()
        running = asyncio.create_task(worker.run(stop)) if config.jobs_in_web else None
        try:
            yield
        finally:
            if running is not None:
                stop.set()
                try:
                    await running
                except Exception as error:
                    log.warning("The web process's worker ended badly (%s).", type(error).__name__)
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
    app.state.mailer = built.mailer
    app.state.worker = worker
    app.state.passwords = Passwords.from_config(config)
    app.state.breach_lookup = breach_lookup if breach_lookup is not None else ask_range
    #: Every permission the kernel or an installed module declares: an owner
    #: holds them all (14.8).
    app.state.declared_permissions = KERNEL_PERMISSIONS | frozenset(
        permission["key"]
        for module in installed
        for permission in module.manifest.raw.get("permissions", [])
        if isinstance(permission, dict) and isinstance(permission.get("key"), str)
    )
    install_handlers(app)

    app.include_router(kernel_router, prefix="/api/kernel")
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(sign_up_router, prefix="/api/auth")
    app.include_router(codes_router, prefix="/api/auth")
    app.include_router(resets_router, prefix="/api/auth")
    app.include_router(email_change_router, prefix="/api/auth")
    app.include_router(password_change_router, prefix="/api/auth")
    app.include_router(totp_router, prefix="/api/auth")
    app.include_router(passkeys_router, prefix="/api/auth")
    app.include_router(factor_undo_router, prefix="/api/auth")
    for module in installed:
        if module.router is not None:
            app.include_router(
                module.router,
                prefix=f"/api/{module.id}",
                dependencies=[Depends(require_module(module.id))],
            )
    # Last: the kernel's files, then every other address (kernel.shell).
    shell.install(app, built.public, app_shell)

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
    app.add_middleware(shell.HeadAsGet)  # every answer within, errors too, loses its body
    app.add_middleware(AccessLog)  # outermost: the whole request, the final status
    return app
