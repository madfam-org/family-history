# family-history web: Next.js 16.3.8 standalone server (landing + app, routed by host).
# Build context: the repository root (pnpm workspace).
#   docker build -f apps/web/Dockerfile -t ghcr.io/madfam-org/family-history-web .
#
# Runtime contract (docs/ARCHITECTURE.md): uid 1001, port 3000, read-only root filesystem.
# The only writable paths are /tmp and /app/.next/cache (emptyDir volumes in Kubernetes).
# No secrets and no NEXT_PUBLIC_* values are used at build time; all configuration is runtime env.

FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build
ENV NEXT_TELEMETRY_DISABLED=1 \
    CI=true
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate
WORKDIR /repo

# Workspace manifests first, so dependency layers cache independently of source changes.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile --filter @family-history/web...

COPY apps/web apps/web
RUN pnpm --filter @family-history/web run build \
 && test -f apps/web/.next/standalone/apps/web/server.js

FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

# The runtime needs only node. npm, npx, corepack and yarn (and their bundled dependencies,
# which trip image scanners) are removed.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
           /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
           /usr/local/bin/yarn /usr/local/bin/yarnpkg /opt/yarn-* \
 && ! command -v npm \
 && ! command -v npx

WORKDIR /app
# Root-owned and therefore read-only for uid 1001.
COPY --from=build /repo/apps/web/.next/standalone ./
COPY --from=build /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build /repo/apps/web/public ./apps/web/public

# Next.js writes its cache under the app's .next/cache; point it at the writable volume.
RUN mkdir -p /app/.next/cache \
 && chown 1001:1001 /app/.next/cache \
 && ln -s /app/.next/cache /app/apps/web/.next/cache \
 && test -f /app/apps/web/server.js

USER 1001
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD wget -q -O /dev/null http://127.0.0.1:3000/api/health || exit 1
CMD ["node", "apps/web/server.js"]
