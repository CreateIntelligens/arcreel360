# syntax=docker/dockerfile:1

FROM node:22-slim AS builder

RUN npm install -g pnpm@11.2.2

FROM node:22-slim AS runner

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gettext-base nginx \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default \
    && mkdir -p \
        /build \
        /tmp/.npm \
        /tmp/.pnpm \
        /usr/share/nginx/html \
        /etc/nginx/conf.d \
        /etc/nginx/templates \
        /var/cache/nginx \
        /var/lib/nginx \
        /var/log/nginx \
        /var/run \
        /run \
    && chown -R 1000:1000 \
        /build \
        /tmp/.npm \
        /tmp/.pnpm \
        /usr/share/nginx/html \
        /etc/nginx/conf.d \
        /etc/nginx/templates \
        /var/cache/nginx \
        /var/lib/nginx \
        /var/log/nginx \
        /var/run \
        /run

COPY --from=builder /usr/local/lib/node_modules/pnpm /usr/local/lib/node_modules/pnpm
RUN printf '#!/bin/sh\nexec node /usr/local/lib/node_modules/pnpm/bin/pnpm.cjs "$@"\n' > /usr/local/bin/pnpm \
    && chmod 0755 /usr/local/bin/pnpm

COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/arcreel-frontend-entrypoint

WORKDIR /build

ENV HOME=/tmp \
    NGINX_CONF=/etc/nginx/conf.d/default.conf \
    NGINX_ROOT=/build/dist \
    NGINX_TEMPLATE=/etc/nginx/templates/default.conf.template \
    PNPM_HOME=/tmp/.pnpm \
    PORT=1241 \
    npm_config_cache=/tmp/.npm

EXPOSE 1241

USER 1000:1000

ENTRYPOINT ["/usr/local/bin/arcreel-frontend-entrypoint"]
CMD ["nginx", "-g", "daemon off;"]
