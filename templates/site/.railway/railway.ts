// This site on Railway, as code (decision 0048): its web service, built from the
// Dockerfile, and a Postgres beside it. Railway doesn't read this file on deploy:
// it's applied from the site's folder, linked to its project (README.md, "Deploying"):
//
//   npm ci                  once: the SDK this file imports (package.json, beside .railway/)
//   railway link            the site's project and environment
//   railway config plan     what it would change: read-only
//   railway config apply    the change, after reading the plan
//
// It owns only what it declares (`partial`): a worker or a bucket added later is left
// alone. But a variable on the web service that isn't listed below is deleted by the
// next apply, so every setting the site may have is here: a fixed value, a reference,
// or `preserve()`, which keeps what the site's owner typed into Railway and makes
// nothing while it's unset. Secrets are never written here. `mechframe add` adds a
// module's settings, as .env.example's; every setting the kernel reads is here.
import { defineRailway, postgres, preserve, project, service } from "railway/iac";

export const partial = "web";

export default defineRailway((ctx) => {
  const db = postgres("postgres");
  const web = service("web", {
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    // A migration that fails stops the deploy before it takes traffic.
    preDeploy: "python -m app.migrations upgrade",
    healthcheck: "/api/kernel/health",
    healthcheckTimeout: 120,
    // Railway restarts a crashed service by default (ON_FAILURE): five tries here.
    deploy: { restartPolicyMaxRetries: 5 },
    env: {
      DATABASE_URL: db.env.DATABASE_URL,
      SITE_NAME: "__SITE_NAME__",
      DEBUG: "false",
      MODULES: "*",
      LOG_FORMAT: "json",
      JOBS_IN_WEB: "true",
      // Railway's edge writes the visitor's address here, and is the only way in.
      CLIENT_IP_HEADER: "X-Real-IP",
      FORWARDED_ALLOW_IPS: "*",
      // Typed into Railway by the site's owner (.env.example says what each is).
      SITE_URL: preserve(),
      SECRET_KEY: preserve(),
      ENCRYPTION_KEYS: preserve(),
      SENTRY_DSN: preserve(),
      MAIL_FROM: preserve(),
      MAIL_FROM_NAME: preserve(),
      SMTP_HOST: preserve(),
      SMTP_PORT: preserve(),
      SMTP_USERNAME: preserve(),
      SMTP_PASSWORD: preserve(),
      RESEND_API_KEY: preserve(),
      STORAGE_ENDPOINT_URL: preserve(),
      STORAGE_ACCESS_KEY_ID: preserve(),
      STORAGE_SECRET_ACCESS_KEY: preserve(),
      STORAGE_BUCKET: preserve(),
      STORAGE_PUBLIC_BUCKET: preserve(),
      STORAGE_PUBLIC_URL: preserve(),
      SIGN_UP_MODE: preserve(),
      CORS_ORIGINS: preserve(),
      HSTS_MAX_AGE: preserve(),
      ROBOTS_NOINDEX: preserve(),
      SENTRY_ENVIRONMENT: preserve(),
      LOG_LEVEL: preserve(),
      // The kernel's defaults while unset (.env.example's tuning); WEB_DIST is the Dockerfile's.
      WEB_DIST: preserve(),
      JOBS_CONCURRENCY: preserve(),
      JOBS_POLL_SECONDS: preserve(),
      JOBS_DRAIN_SECONDS: preserve(),
      AUDIT_KEEP_DAYS: preserve(),
      DB_POOL_SIZE: preserve(),
      DB_MAX_OVERFLOW: preserve(),
      MODULES_CACHE_SECONDS: preserve(),
      MAX_BODY_BYTES: preserve(),
      STORAGE_REGION: preserve(),
      STORAGE_MAX_BYTES: preserve(),
      RATE_LIMIT_ENABLED: preserve(),
      RATE_LIMIT_STORAGE: preserve(),
      ARGON2_MEMORY_KIB: preserve(),
      ARGON2_TIME_COST: preserve(),
      ARGON2_LANES: preserve(),
      ARGON2_CONCURRENCY: preserve(),
      // --- The modules' settings, added by mechframe add ---
    },
  });
  return project(ctx.projectName ?? "__SITE_NAME__", { resources: [web, db] });
});
