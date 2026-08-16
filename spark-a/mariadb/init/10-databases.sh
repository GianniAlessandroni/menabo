#!/usr/bin/env bash
# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     spark-a/mariadb/init/10-databases.sh
#  Purpose:  First-boot provisioning: wordpress and metrics databases, one
#            least-privilege user each. Agents get NO database credentials
#            (SPEC §4) — enforced by grants, not convention.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
set -euo pipefail

mariadb --protocol=socket -uroot <<SQL
CREATE DATABASE IF NOT EXISTS wordpress CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'wordpress'@'%' IDENTIFIED BY '${WORDPRESS_DB_PASSWORD}';
GRANT ALL PRIVILEGES ON wordpress.* TO 'wordpress'@'%';

CREATE DATABASE IF NOT EXISTS metrics CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'metrics_collector'@'%' IDENTIFIED BY '${METRICS_DB_PASSWORD}';
GRANT SELECT, INSERT, UPDATE, DELETE ON metrics.* TO 'metrics_collector'@'%';

FLUSH PRIVILEGES;
SQL

echo "10-databases.sh: wordpress and metrics databases provisioned."

# The canonical schema lives in metrics/schema.sql (mounted read-only here);
# it is self-contained (CREATE DATABASE IF NOT EXISTS + USE metrics).
mariadb --protocol=socket -uroot < /opt/menabo/metrics-schema.sql
echo "10-databases.sh: metrics schema applied."
