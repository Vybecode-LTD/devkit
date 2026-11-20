# This site's image (README.md, "Deploying"): Node builds web/dist, then Python
# runs the app behind the host's proxy. Railway uses it as it is: its start
# command is the CMD below, and it binds the PORT Railway gives.

FROM node:22-bookworm-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json web/.npmrc ./
# The lockfile only, with the dev tools the build needs, and no install scripts (.npmrc).
RUN npm ci --include=dev
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    WEB_DIST=/app/web/dist
WORKDIR /app
COPY requirements.txt ./
# Hash-pinned, wheels only (SPEC.md section 15).
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt
COPY backend/ backend/
COPY --from=web /app/web/dist web/dist
RUN useradd --create-home --uid 10001 site
USER site
EXPOSE 8000
# Behind the edge, the request's scheme and peer come from its headers: uvicorn reads
# them from the addresses FORWARDED_ALLOW_IPS names (* on Railway, .env.example).
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
