#!/usr/bin/env bash
# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     scripts/setup-wordpress.sh
#  Purpose:  Bootstrap WordPress: core install, mcp-adapter plugin (pinned),
#            the impaginatore Contributor user and its Application Password.
#            Idempotent except the Application Password (printed once).
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
set -euo pipefail

# why: pinned versions — never `latest` (CODING-STANDARDS §6)
WP_CLI_VERSION=2.12.0
MCP_ADAPTER_VERSION=v0.6.1

cd "$(git rev-parse --show-toplevel)/spark-a"
set -a
# shellcheck disable=SC1091
source .env
set +a

wp() {
    docker compose exec -T -u www-data wordpress php /tmp/wp-cli.phar --path=/var/www/html "$@"
}

echo "setup-wordpress: installing wp-cli ${WP_CLI_VERSION} in the container..."
docker compose exec -T wordpress bash -c \
    "curl -fsSL -o /tmp/wp-cli.phar https://github.com/wp-cli/wp-cli/releases/download/v${WP_CLI_VERSION}/wp-cli-${WP_CLI_VERSION}.phar && chmod 0644 /tmp/wp-cli.phar"

if wp core is-installed 2>/dev/null; then
    echo "setup-wordpress: core already installed, skipped."
else
    wp core install \
        --url="${STAGING_URL:?}" \
        --title="${WORDPRESS_SITE_TITLE:?}" \
        --admin_user="${WORDPRESS_ADMIN_USER:?}" \
        --admin_password="${WORDPRESS_ADMIN_PASSWORD:?}" \
        --admin_email="${WORDPRESS_ADMIN_EMAIL:?}" \
        --skip-email
    echo "setup-wordpress: core installed."
fi

if wp plugin is-installed mcp-adapter 2>/dev/null; then
    echo "setup-wordpress: mcp-adapter already installed, skipped."
else
    wp plugin install \
        "https://github.com/WordPress/mcp-adapter/releases/download/${MCP_ADAPTER_VERSION}/mcp-adapter.zip" \
        --activate
    echo "setup-wordpress: mcp-adapter ${MCP_ADAPTER_VERSION} installed and activated."
fi

# The publication gate (SPEC §2.1): Contributor can draft, never publish.
if wp user get impaginatore --field=user_login 2>/dev/null; then
    echo "setup-wordpress: user impaginatore already exists, skipped."
else
    wp user create impaginatore impaginatore@redazione.local \
        --role=contributor --user_pass="$(openssl rand -base64 24)" >/dev/null
    echo "setup-wordpress: user impaginatore created with role Contributor."
fi

echo "setup-wordpress: creating a fresh Application Password for impaginatore..."
app_password="$(wp user application-password create impaginatore hermes-mcp --porcelain)"
basic_auth="$(printf 'impaginatore:%s' "$app_password" | base64 -w0)"
echo
echo "  Paste into spark-a/agents/impaginatore/.env:"
echo "  WORDPRESS_MCP_BASIC_AUTH=${basic_auth}"
echo
echo "setup-wordpress: done."
