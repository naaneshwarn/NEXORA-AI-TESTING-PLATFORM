# Build the React dashboard, then serve the static bundle with nginx.
#
# Build context is the repository root (see docker-compose.yml):
#   docker build -f apps/web/Dockerfile .

# --- stage 1: build -------------------------------------------------------
FROM node:20-slim AS build

WORKDIR /repo

# Workspace root install first: @nexora/web depends on the local
# @nexora/shared workspace package, so the lockfile/workspace layout must be
# in place before anything is built.
COPY package.json package-lock.json* ./
COPY apps/web/package.json ./apps/web/package.json
COPY apps/api/package.json ./apps/api/package.json
COPY packages/shared/package.json ./packages/shared/package.json
RUN npm install --no-audit --no-fund

COPY packages/shared ./packages/shared
COPY apps/web ./apps/web

# Optional build-time API key / backend base URL (see .env.example).
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_API_KEY=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_API_KEY=${VITE_API_KEY}

RUN npm run build --workspace @nexora/shared \
    && npm run build --workspace @nexora/web

# --- stage 2: serve -------------------------------------------------------
FROM nginx:1.27-alpine

COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
