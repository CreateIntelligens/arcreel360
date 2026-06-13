#!/bin/sh
set -eu

cd "${FRONTEND_WORKDIR:-/build}"

pnpm_home="${PNPM_HOME:-/tmp/.pnpm}"
npm_cache="${npm_config_cache:-/tmp/.npm}"
nginx_root="${NGINX_ROOT:-/build/dist}"
nginx_template="${NGINX_TEMPLATE:-/etc/nginx/templates/default.conf.template}"
nginx_conf="${NGINX_CONF:-/etc/nginx/conf.d/default.conf}"

mkdir -p "$pnpm_home" "$npm_cache" "$nginx_root"

if [ "${FRONTEND_SKIP_INSTALL:-0}" != "1" ]; then
    pnpm install --frozen-lockfile
fi

if [ "${FRONTEND_SKIP_BUILD:-0}" != "1" ]; then
    pnpm build
fi

if [ -f "$nginx_template" ]; then
    defined_envs="$(printf '${%s} ' $(env | cut -d= -f1))"
    envsubst "$defined_envs" < "$nginx_template" > "$nginx_conf"
fi

exec "$@"
